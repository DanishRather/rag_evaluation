"""Remove a run and the rows that belong only to it."""

from app.domain.models import Finding, Job, JudgeUsage, MetricResult, ProgressEvent, Report, RewriteRecord, Run, Trace

_RUN_ROWS = (Job, ProgressEvent, Trace, MetricResult, Finding, Report, JudgeUsage, RewriteRecord)


def purge_run(repository, run_id: str) -> None:
    for kind in _RUN_ROWS:
        repository.remove(kind, run_id=run_id)
    repository.remove(Run, id=run_id)
