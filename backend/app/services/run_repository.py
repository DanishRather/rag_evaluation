from __future__ import annotations

from typing import Protocol, TypeVar

from app.domain.models import (
    CalibrationLabel,
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
)

T = TypeVar("T")

ENTITY_TYPES = (
    Project,
    System,
    SystemConfig,
    Secret,
    Dataset,
    TestCase,
    Run,
    Job,
    Trace,
    MetricResult,
    Finding,
    Report,
    CalibrationLabel,
    ProgressEvent,
    JudgeUsage,
    JudgeVerdict,
    RewriteRecord,
)


class RunRepository(Protocol):
    def get(self, kind: type[T], id: str) -> T | None: ...

    def add(self, entity: object) -> None: ...

    def list(self, kind: type[T], **filters: object) -> list[T]: ...

    def remove(self, kind: type[T], **filters: object) -> None: ...
