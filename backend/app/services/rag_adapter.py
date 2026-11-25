from typing import Protocol

from app.domain.models import Capabilities, QueryRequest, Trace


class RAGAdapter(Protocol):
    def run_query(self, request: QueryRequest) -> Trace: ...

    def capabilities(self) -> Capabilities: ...
