import json

from app.domain.models import RenderedReport, Report


class JsonReportRenderer:
    def render(self, report: Report) -> RenderedReport:
        body = json.dumps(report.model, indent=2, sort_keys=True).encode()
        return RenderedReport("application/json", f"{report.run_id}.json", body)
