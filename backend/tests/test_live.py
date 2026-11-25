import threading
import time

import pytest

from app.domain.errors import DomainError
from app.domain.models import SystemConfig, new_id
from app.main import process_jobs
from tests.support import open_container, seed, start_run

_CSV = "\n".join(
    [
        "question,expected_answer,gold_passage",
        "first,30 days,alpha beta gamma delta",
        "broken,30 days,alpha beta gamma delta",
        "third,30 days,alpha beta gamma delta",
    ]
)


def test_live_lists_every_question_in_queue_order_before_the_run_starts(tmp_path, monkeypatch):
    container, _box, _judge = open_container(tmp_path, monkeypatch)
    project, config, dataset = seed(container, _CSV)
    earlier = start_run(container, project, dataset, config)
    run = start_run(container, project, dataset, config)
    live = container.run_service.live(run.id)
    assert live["status"] == "queued"
    assert (live["total"], live["done"], live["failed"], live["remaining"], live["waiting"]) == (3, 0, 0, 3, 3)
    assert [item["question"] for item in live["items"]] == ["first", "broken", "third"]
    assert {item["state"] for item in live["items"]} == {"queued"}
    assert live["runs_ahead"] == 1
    assert container.run_service.live(earlier.id)["runs_ahead"] == 0


def test_live_counts_done_and_failed_questions_after_the_run(tmp_path, monkeypatch):
    container, box, _judge = open_container(tmp_path, monkeypatch)
    box.fail_questions.add("broken")
    project, config, dataset = seed(container, _CSV)
    run = start_run(container, project, dataset, config)
    container.run_service.execute(run.id)
    live = container.run_service.live(run.id)
    assert live["status"] == "succeeded"
    assert (live["total"], live["done"], live["failed"], live["remaining"], live["running"]) == (3, 2, 1, 0, 0)
    states = {item["question"]: item for item in live["items"]}
    assert states["first"]["state"] == "done"
    assert states["first"]["answer"] == "30 days"
    assert states["first"]["started_at"] and states["first"]["finished_at"]
    assert states["broken"]["state"] == "failed"
    assert states["broken"]["error"] == "forced target error"
    assert any(entry["kind"] == "question_started" for entry in live["log"])


def test_cancelled_run_marks_unstarted_questions_not_run(tmp_path, monkeypatch):
    container, _box, _judge = open_container(tmp_path, monkeypatch)
    project, config, dataset = seed(container, _CSV)
    run = start_run(container, project, dataset, config)
    container.run_service.cancel(run.id)
    live = container.run_service.live(run.id)
    assert live["status"] == "cancelled"
    assert {item["state"] for item in live["items"]} == {"not_run"}


def test_failed_run_reports_why(tmp_path, monkeypatch):
    container, _box, _judge = open_container(tmp_path, monkeypatch)
    project, config, dataset = seed(container, _CSV)
    run = start_run(container, project, dataset, config)

    def broken(*_args, **_kwargs):
        raise RuntimeError("adapter exploded")

    container.run_service._open_adapter = broken
    try:
        container.run_service.execute(run.id)
    except RuntimeError:
        pass
    live = container.run_service.live(run.id)
    assert live["status"] == "failed"
    assert live["message"] == "Run failed: adapter exploded"


def test_worker_loop_claims_and_finishes_a_queued_run(tmp_path, monkeypatch):
    container, box, _judge = open_container(tmp_path, monkeypatch)
    project, config, dataset = seed(container, _CSV)
    run = start_run(container, project, dataset, config)
    stop = threading.Event()
    thread = threading.Thread(target=process_jobs, args=(container, stop), daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline and container.run_service.get(run.id).status != "succeeded":
        time.sleep(0.05)
    stop.set()
    thread.join(timeout=5)
    assert container.run_service.get(run.id).status == "succeeded"
    assert [call.question for call in box.calls] == ["first", "broken", "third"]
    assert container.worker.alive is False


def test_requeue_running_returns_an_interrupted_job_to_the_queue(tmp_path, monkeypatch):
    container, _box, _judge = open_container(tmp_path, monkeypatch)
    project, config, dataset = seed(container, _CSV)
    run = start_run(container, project, dataset, config)
    claimed = container.job_queue.claim()
    assert claimed is not None and claimed.run_id == run.id
    assert container.job_queue.claim() is None
    assert container.job_queue.requeue_running() == 1
    again = container.job_queue.claim()
    assert again is not None and again.run_id == run.id


def test_a_fixed_question_connection_cannot_start_resume_or_be_rejudged(tmp_path, monkeypatch):
    container, _box, _judge = open_container(tmp_path, monkeypatch)
    project, config, dataset = seed(container, _CSV)
    broken = SystemConfig(
        id=new_id(),
        system_id=config.system_id,
        version=2,
        adapter_type="http",
        adapter_settings={"url": "http://127.0.0.1:9/runs", "request_template": "ping", "encoding": "json"},
        profile_settings={},
    )
    container.repository.add(broken)
    with pytest.raises(DomainError, match="fixed text"):
        start_run(container, project, dataset, broken)
    run = start_run(container, project, dataset, config)
    run.system_config_version_id = broken.id
    run.status = "failed"
    container.repository.add(run)
    with pytest.raises(DomainError, match="fixed text"):
        container.run_service.resume(run.id)
    with pytest.raises(DomainError, match="nothing to judge"):
        container.run_service.reevaluate(run.id, None, None, None)
    container.run_service.delete(run.id)
    assert container.run_service.list_runs(project.id) == []
