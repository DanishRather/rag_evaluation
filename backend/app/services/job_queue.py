from typing import Protocol

from app.domain.models import Job


class JobQueue(Protocol):
    def enqueue(self, run_id: str) -> Job: ...

    def claim(self) -> Job | None: ...

    def requeue_running(self) -> int: ...
