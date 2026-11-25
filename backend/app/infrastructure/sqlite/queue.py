from sqlalchemy import text

from app.domain.models import Job, new_id, utc_now

_CLAIM = """
UPDATE jobs
SET status = 'running', locked_at = CURRENT_TIMESTAMP, attempts = attempts + 1
WHERE id = (
  SELECT id FROM jobs
  WHERE status = 'queued'
  ORDER BY created_at
  LIMIT 1
)
RETURNING id, run_id, status, attempts, locked_at, created_at
"""

_REQUEUE = "UPDATE jobs SET status = 'queued', locked_at = NULL WHERE status = 'running'"


class SqliteJobQueue:
    def __init__(self, engine, repository, lock) -> None:
        self._engine = engine
        self._repository = repository
        self._lock = lock

    def enqueue(self, run_id: str) -> Job:
        existing = self._repository.list(Job, run_id=run_id)
        if existing:
            job = existing[0]
            job.status = "queued"
            job.locked_at = None
            self._repository.add(job)
            return job
        job = Job(
            id=new_id(),
            run_id=run_id,
            status="queued",
            attempts=0,
            locked_at=None,
            created_at=utc_now(),
        )
        self._repository.add(job)
        return job

    def requeue_running(self) -> int:
        with self._lock, self._engine.begin() as connection:
            return connection.execute(text(_REQUEUE)).rowcount or 0

    def claim(self) -> Job | None:
        with self._lock, self._engine.begin() as connection:
            row = connection.execute(text(_CLAIM)).mappings().first()
        if row is None:
            return None
        return Job(
            id=row["id"],
            run_id=row["run_id"],
            status=row["status"],
            attempts=int(row["attempts"]),
            locked_at=None if row["locked_at"] is None else str(row["locked_at"]),
            created_at=str(row["created_at"]),
        )
