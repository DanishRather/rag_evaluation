from app.domain.errors import DomainError
from app.domain.models import RenderedReport, Report
from app.infrastructure.renderers.html_renderer import HtmlReportRenderer


class PdfReportRenderer:
    def __init__(self, html: HtmlReportRenderer | None = None) -> None:
        self._html = html or HtmlReportRenderer()

    def render(self, report: Report) -> RenderedReport:
        rendered = self._html.render(report)
        try:
            from weasyprint import HTML
        except Exception as exc:
            raise DomainError(
                "run_failed",
                "PDF rendering is unavailable because WeasyPrint is not installed",
            ) from exc
        pdf = HTML(string=rendered.body.decode()).write_pdf()
        return RenderedReport("application/pdf", f"{report.run_id}.pdf", pdf)
