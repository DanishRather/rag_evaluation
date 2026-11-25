"""Composition root. The only application module that imports infrastructure."""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from importlib.metadata import entry_points
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import install_error_handlers
from app.api.routers.calibration import router as calibration_router
from app.api.routers.datasets import router as datasets_router
from app.api.routers.projects import router as projects_router
from app.api.routers.reports import router as reports_router
from app.api.routers.runs import router as runs_router
from app.api.routers.systems import router as systems_router
from app.domain.errors import DomainError
from app.domain.models import WorkerState, utc_now
from app.evaluators.chunking import ChunkMetrics
from app.evaluators.history import HistoryMetrics
from app.evaluators.quality import CorrectnessMetric, FaithfulnessMetric
from app.evaluators.retrieval import HitRateMetric, MrrMetric, PrecisionAtKMetric, RecallAtKMetric
from app.evaluators.runtime import RuntimeMetrics
from app.evaluators.variance import VarianceMetrics
from app.infrastructure.adapters.http_adapter import HttpAdapter
from app.infrastructure.adapters.openai_adapter import OpenAIChatAdapter
from app.infrastructure.adapters.python_adapter import PythonObjectAdapter
from app.infrastructure.adapters.secrets import seal
from app.infrastructure.judge.agno_judge import AgnoJudge
from app.infrastructure.renderers.html_renderer import HtmlReportRenderer
from app.infrastructure.renderers.json_renderer import JsonReportRenderer
from app.infrastructure.renderers.pdf_renderer import PdfReportRenderer
from app.infrastructure.sqlite.engine import ensure_sqlite_path, make_engine
from app.infrastructure.sqlite.queue import SqliteJobQueue
from app.infrastructure.sqlite.repository import SqliteRunRepository
from app.services.calibration_service import CalibrationService
from app.services.dataset_service import DatasetService
from app.services.diagnosis_service import DiagnosisService
from app.services.judge import Judge
from app.services.project_service import ProjectService
from app.services.report_service import ReportService
from app.services.run_service import RunService
from app.services.system_service import SystemService

_BACKEND = Path(__file__).resolve().parents[1]


@dataclass
class Container:
    engine: object
    repository: SqliteRunRepository
    job_queue: SqliteJobQueue
    judge: Judge
    adapter_factories: dict
    project_service: ProjectService
    system_service: SystemService
    dataset_service: DatasetService
    run_service: RunService
    diagnosis_service: DiagnosisService
    report_service: ReportService
    calibration_service: CalibrationService
    worker: WorkerState


def build_evaluators(judge: Judge) -> list:
    return [
        CorrectnessMetric(judge),
        FaithfulnessMetric(judge),
        HitRateMetric(judge),
        MrrMetric(judge),
        PrecisionAtKMetric(judge),
        RecallAtKMetric(judge),
        ChunkMetrics(judge),
        HistoryMetrics(judge),
        RuntimeMetrics(),
        VarianceMetrics(),
    ]


def default_adapters() -> dict:
    factories = {
        "http": HttpAdapter,
        "openai_chat": OpenAIChatAdapter,
    }
    if os.environ.get("EVAL_ALLOW_PYTHON_ADAPTERS") == "1":
        factories["python"] = PythonObjectAdapter
    try:
        discovered = entry_points(group="eval_agent.adapters")
    except Exception:
        discovered = ()
    for item in discovered:
        factories[item.name] = item.load()
    return factories


def migrate(database_url: str) -> None:
    from alembic import command
    from alembic.config import Config

    ensure_sqlite_path(database_url)
    config = Config(str(_BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(_BACKEND / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")


def create_container(
    database_url: str | None = None,
    *,
    judge: Judge | None = None,
    secondary_judge: Judge | None = None,
    adapter_factories: dict | None = None,
) -> Container:
    url = database_url or os.environ.get("EVAL_DATABASE_URL", "sqlite:///./data/eval.db")
    migrate(url)
    engine, lock = make_engine(url)
    repository = SqliteRunRepository(engine, lock)
    queue = SqliteJobQueue(engine, repository, lock)
    primary = judge if judge is not None else AgnoJudge(repository)
    secondary = secondary_judge if secondary_judge is not None else AgnoJudge(repository)
    factories = default_adapters() if adapter_factories is None else adapter_factories
    diagnosis = DiagnosisService(repository)
    calibration = CalibrationService(repository)
    html = HtmlReportRenderer()
    renderers = {
        "json": JsonReportRenderer(),
        "html": html,
        "pdf": PdfReportRenderer(html),
    }
    reports = ReportService(repository, primary, renderers, diagnosis, calibration)
    worker = WorkerState()
    runs = RunService(
        repository,
        queue,
        primary,
        secondary,
        factories,
        build_evaluators,
        diagnosis,
        reports,
        worker=worker,
    )
    return Container(
        engine=engine,
        repository=repository,
        job_queue=queue,
        judge=primary,
        adapter_factories=factories,
        project_service=ProjectService(repository),
        system_service=SystemService(repository, factories, seal),
        dataset_service=DatasetService(repository),
        run_service=runs,
        diagnosis_service=diagnosis,
        report_service=reports,
        calibration_service=calibration,
        worker=worker,
    )


def process_jobs(container: Container, stop: threading.Event | None = None) -> None:
    state = container.worker
    state.alive = True
    try:
        while stop is None or not stop.is_set():
            state.heartbeat = utc_now()
            job = container.job_queue.claim()
            if job is None:
                if stop is None:
                    time.sleep(0.5)
                else:
                    stop.wait(0.5)
                continue
            state.current_run_id = job.run_id
            try:
                container.run_service.execute(job.run_id)
            except DomainError as exc:
                logging.warning("run %s failed: %s", job.run_id, exc)
            except Exception:
                logging.exception("worker failed run %s", job.run_id)
            finally:
                state.current_run_id = None
    finally:
        state.alive = False


def start_embedded_worker(container: Container) -> threading.Thread:
    """Run queued jobs inside the API process. A restart re-queues jobs that were mid-run."""
    container.worker.embedded = True
    container.job_queue.requeue_running()
    thread = threading.Thread(target=process_jobs, args=(container,), name="eval-worker", daemon=True)
    thread.start()
    return thread


def create_app(database_url: str | None = None, **overrides) -> FastAPI:
    container = create_container(database_url, **overrides)
    app = FastAPI(title="RAG Evaluation Platform")
    app.state.container = container
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:27464", "http://127.0.0.1:27464"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    install_error_handlers(app)
    for router in (
        projects_router,
        systems_router,
        datasets_router,
        reports_router,
        runs_router,
        calibration_router,
    ):
        app.include_router(router, prefix="/api")
    return app


def serve() -> None:
    import uvicorn

    app = create_app()
    if os.environ.get("EVAL_EMBEDDED_WORKER", "1") != "0":
        start_embedded_worker(app.state.container)
    uvicorn.run(app, host="127.0.0.1", port=27463)
