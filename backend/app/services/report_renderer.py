from typing import Protocol

from app.domain.models import RenderedReport, Report


class ReportRenderer(Protocol):
    def render(self, report: Report) -> RenderedReport: ...
