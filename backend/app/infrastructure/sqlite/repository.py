"""One SQLite repository for every stored entity."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass

from sqlalchemy import func
from sqlalchemy.orm import Session, sessionmaker

from app.domain.models import (
    CalibrationLabel,
    Chunk,
    Dataset,
    Finding,
    Job,
    JudgeUsage,
    JudgeVerdict,
    MetricResult,
    ProgressEvent,
    Project,
    Report,
    RewriteRecord,
    Run,
    Secret,
    System,
    SystemConfig,
    TestCase,
    Trace,
    new_id,
)
from app.infrastructure.sqlite.orm import (
    CalibrationLabelRow,
    DatasetRow,
    FindingRow,
    JobRow,
    JudgeUsageRow,
    JudgeVerdictRow,
    MetricResultRow,
    ProgressEventRow,
    ProjectRow,
    ReportRow,
    RewriteRecordRow,
    RunRow,
    SecretRow,
    SystemConfigRow,
    SystemRow,
    TestCaseRow,
    TraceChunkRow,
    TraceRow,
)


@dataclass(frozen=True)
class Spec:
    cls: type
    row: type
    fields: tuple[str, ...]
    unique: tuple[str, ...]
    json_fields: frozenset[str] = frozenset()
    bool_fields: frozenset[str] = frozenset()
    order: tuple[str, ...] = ()


SPECS: dict[type, Spec] = {
    Project: Spec(Project, ProjectRow, ("id", "name", "created_at"), ("id",), order=("created_at",)),
    System: Spec(System, SystemRow, ("id", "project_id", "name", "created_at"), ("id",), order=("created_at",)),
    SystemConfig: Spec(
        SystemConfig,
        SystemConfigRow,
        ("id", "system_id", "version", "adapter_type", "adapter_settings", "profile_settings", "secret_id"),
        ("system_id", "version"),
        json_fields=frozenset({"adapter_settings", "profile_settings"}),
        order=("version",),
    ),
    Secret: Spec(Secret, SecretRow, ("id", "project_id", "ciphertext", "nonce"), ("id",)),
    Dataset: Spec(
        Dataset,
        DatasetRow,
        ("id", "project_id", "name", "source_filename", "column_map", "headers", "raw_rows", "created_at"),
        ("id",),
        json_fields=frozenset({"column_map", "headers", "raw_rows"}),
        order=("created_at",),
    ),
    TestCase: Spec(
        TestCase,
        TestCaseRow,
        (
            "id",
            "dataset_id",
            "source_row",
            "conversation_id",
            "turn_index",
            "question",
            "expected_answer",
            "gold_passage",
        ),
        ("dataset_id", "source_row"),
        order=("source_row",),
    ),
    Run: Spec(
        Run,
        RunRow,
        (
            "id",
            "project_id",
            "dataset_id",
            "system_config_version_id",
            "replay_of_run_id",
            "judge_config",
            "evaluator_ids",
            "price_table",
            "repeats",
            "max_concurrency",
            "status",
            "idempotency_key",
            "request_hash",
            "use_judge_cache",
            "target_timeout_s",
            "target_max_attempts",
            "capabilities",
            "created_at",
        ),
        ("id",),
        json_fields=frozenset({"judge_config", "evaluator_ids", "price_table", "capabilities"}),
        bool_fields=frozenset({"use_judge_cache"}),
        order=("created_at",),
    ),
    Job: Spec(
        Job,
        JobRow,
        ("id", "run_id", "status", "attempts", "locked_at", "created_at"),
        ("run_id",),
        order=("created_at",),
    ),
    Trace: Spec(
        Trace,
        TraceRow,
        (
            "id",
            "run_id",
            "test_case_id",
            "conversation_id",
            "turn_index",
            "kind",
            "repeat_index",
            "question",
            "answer",
            "rewritten_query",
            "error",
            "latency_ms",
            "prompt_tokens",
            "completion_tokens",
            "model",
            "status",
        ),
        ("run_id", "test_case_id", "kind", "repeat_index"),
        order=("turn_index", "repeat_index"),
    ),
    MetricResult: Spec(
        MetricResult,
        MetricResultRow,
        (
            "id",
            "run_id",
            "test_case_id",
            "metric_id",
            "value",
            "status",
            "skip_reason",
            "details",
            "rubric_version",
            "judge_model",
            "temperature",
            "judge_role",
            "prompt_hash",
            "repeat_index",
            "judge_slot",
        ),
        ("run_id", "test_case_id", "metric_id", "repeat_index", "judge_slot"),
        json_fields=frozenset({"details"}),
        order=("test_case_id", "metric_id"),
    ),
    Finding: Spec(
        Finding,
        FindingRow,
        ("id", "run_id", "rule_id", "cause", "severity", "count", "example_question_ids", "evidence"),
        ("run_id", "rule_id"),
        json_fields=frozenset({"example_question_ids", "evidence"}),
    ),
    Report: Spec(Report, ReportRow, ("id", "run_id", "model"), ("run_id",), json_fields=frozenset({"model"})),
    CalibrationLabel: Spec(
        CalibrationLabel,
        CalibrationLabelRow,
        ("id", "dataset_id", "test_case_id", "human_correct"),
        ("dataset_id", "test_case_id"),
        bool_fields=frozenset({"human_correct"}),
    ),
    ProgressEvent: Spec(
        ProgressEvent,
        ProgressEventRow,
        ("id", "run_id", "seq", "kind", "message", "payload"),
        ("run_id", "seq"),
        json_fields=frozenset({"payload"}),
        order=("seq",),
    ),
    JudgeVerdict: Spec(
        JudgeVerdict,
        JudgeVerdictRow,
        ("id", "cache_key", "agent", "model_id", "judge_slot", "prompt_hash", "verdict"),
        ("cache_key",),
        json_fields=frozenset({"verdict"}),
    ),
    JudgeUsage: Spec(
        JudgeUsage,
        JudgeUsageRow,
        (
            "id",
            "run_id",
            "test_case_id",
            "agent",
            "judge_slot",
            "model_id",
            "input_tokens",
            "output_tokens",
            "cost",
            "duration",
            "cache_hit",
        ),
        ("id",),
        bool_fields=frozenset({"cache_hit"}),
    ),
    RewriteRecord: Spec(
        RewriteRecord,
        RewriteRecordRow,
        (
            "id",
            "run_id",
            "test_case_id",
            "repeat_index",
            "standalone_question",
            "resolved_pronouns",
            "reason",
        ),
        ("run_id", "test_case_id", "repeat_index"),
        bool_fields=frozenset({"resolved_pronouns"}),
    ),
}


def _column(spec: Spec, name: str) -> str:
    if name in spec.json_fields:
        return f"{name}_json"
    return name


def _dump(entity: object, spec: Spec) -> dict:
    payload: dict = {}
    for name in spec.fields:
        value = getattr(entity, name)
        column = _column(spec, name)
        if name in spec.json_fields:
            payload[column] = json.dumps(value)
        elif name in spec.bool_fields:
            payload[column] = int(bool(value))
        else:
            payload[column] = value
    return payload


def _load(row: object, spec: Spec) -> object:
    kwargs = {}
    for name in spec.fields:
        column = _column(spec, name)
        value = getattr(row, column)
        if name in spec.json_fields:
            value = None if value is None else json.loads(value)
        elif name in spec.bool_fields:
            value = bool(value)
        kwargs[name] = value
    if spec.cls is Trace:
        kwargs["chunks"] = []
    return spec.cls(**kwargs)


def _chunks_for(session: Session, trace_ids: list[str]) -> dict[str, list[Chunk]]:
    grouped: dict[str, list[Chunk]] = {trace_id: [] for trace_id in trace_ids}
    if not trace_ids:
        return grouped
    rows = (
        session.query(TraceChunkRow)
        .filter(TraceChunkRow.trace_id.in_(trace_ids))
        .order_by(TraceChunkRow.rank)
        .all()
    )
    for row in rows:
        grouped.setdefault(row.trace_id, []).append(
            Chunk(
                chunk_key=row.chunk_key,
                rank=row.rank,
                text=row.text,
                score=row.score,
                source=row.source,
                page=row.page,
                token_length=row.token_length,
            )
        )
    return grouped


class SqliteRunRepository:
    def __init__(self, engine, lock: threading.RLock) -> None:
        self._engine = engine
        self._lock = lock
        self._Session = sessionmaker(bind=engine, expire_on_commit=False)

    def get(self, kind: type, id: str):
        spec = SPECS[kind]
        with self._lock, self._Session() as session:
            row = session.get(spec.row, id)
            if row is None:
                return None
            entity = _load(row, spec)
            if kind is Trace:
                entity.chunks = _chunks_for(session, [row.id]).get(row.id, [])
            return entity

    def add(self, entity: object) -> None:
        spec = SPECS[type(entity)]
        with self._lock, self._Session() as session, session.begin():
            if isinstance(entity, ProgressEvent) and entity.seq <= 0:
                current = (
                    session.query(func.max(ProgressEventRow.seq))
                    .filter(ProgressEventRow.run_id == entity.run_id)
                    .scalar()
                )
                entity.seq = int(current or 0) + 1
            payload = _dump(entity, spec)
            existing = (
                session.query(spec.row)
                .filter_by(**{key: payload[key] for key in spec.unique})
                .one_or_none()
            )
            if isinstance(entity, Trace) and existing is not None and existing.status == "ok":
                return
            if existing is None:
                session.add(spec.row(**payload))
                trace_id = payload.get("id")
            else:
                for key, value in payload.items():
                    if key == "id":
                        continue
                    setattr(existing, key, value)
                entity.id = existing.id
                trace_id = existing.id
            if isinstance(entity, Trace):
                session.query(TraceChunkRow).filter(TraceChunkRow.trace_id == trace_id).delete(
                    synchronize_session=False
                )
                for chunk in entity.chunks:
                    session.add(
                        TraceChunkRow(
                            id=new_id(),
                            trace_id=trace_id,
                            rank=chunk.rank,
                            chunk_key=chunk.chunk_key,
                            text=chunk.text,
                            score=chunk.score,
                            source=chunk.source,
                            page=chunk.page,
                            token_length=chunk.token_length,
                        )
                    )

    def list(self, kind: type, **filters: object) -> list:
        spec = SPECS[kind]
        with self._lock, self._Session() as session:
            query = session.query(spec.row)
            for key, value in filters.items():
                query = query.filter(getattr(spec.row, _column(spec, key)) == value)
            for name in spec.order:
                query = query.order_by(getattr(spec.row, _column(spec, name)))
            rows = query.all()
            entities = [_load(row, spec) for row in rows]
            if kind is Trace and entities:
                grouped = _chunks_for(session, [row.id for row in rows])
                for entity in entities:
                    entity.chunks = grouped.get(entity.id, [])
            return entities

    def remove(self, kind: type, **filters: object) -> None:
        spec = SPECS[kind]
        with self._lock, self._Session() as session, session.begin():
            query = session.query(spec.row)
            for key, value in filters.items():
                query = query.filter(getattr(spec.row, _column(spec, key)) == value)
            if kind is Trace:
                ids = [row.id for row in query.all()]
                if ids:
                    session.query(TraceChunkRow).filter(TraceChunkRow.trace_id.in_(ids)).delete(
                        synchronize_session=False
                    )
                    session.query(TraceRow).filter(TraceRow.id.in_(ids)).delete(synchronize_session=False)
                return
            query.delete(synchronize_session=False)
