from html import escape

from app.domain.models import RenderedReport, Report

_SECTIONS = (
    "header",
    "score_summary",
    "skipped",
    "failure_causes",
    "findings",
    "setup_table",
    "compare",
    "calibration",
)


class HtmlReportRenderer:
    def render(self, report: Report) -> RenderedReport:
        model = report.model
        parts = [
            "<!DOCTYPE html>",
            "<html lang='en'><head><meta charset='utf-8'>",
            f"<title>Run {escape(report.run_id)}</title>",
            "<style>",
            "body{font-family:Georgia,serif;margin:2rem;line-height:1.45;color:#1c1915;background:#f7f3ea}",
            "table{border-collapse:collapse;width:100%}td,th{border:1px solid #d9d1c3;padding:.4rem;text-align:left}",
            "h1,h2{font-weight:600} .muted{color:#5c564c}",
            "</style></head><body>",
            f"<h1>Evaluation report</h1>",
        ]
        parts.append(_section("Run header", _header(model.get("header") or {})))
        parts.append(_section("Score summary", _metrics(model.get("score_summary") or [])))
        parts.append(_section("What could not be measured", _skipped(model.get("skipped") or [])))
        parts.append(_section("Failure-cause counts", _causes(model.get("failure_causes") or {})))
        parts.append(_section("Findings", _findings(model.get("findings") or [])))
        parts.append(_section("Setup table", _setup(model.get("setup_table") or [])))
        parts.append(_section("Compare block", _compare(model.get("compare"))))
        parts.append(_section("Calibration banner", _calibration(model.get("calibration") or {})))
        missing = [name for name in _SECTIONS if name not in model]
        if missing:
            parts.append(f"<p class='muted'>Missing sections: {escape(', '.join(missing))}</p>")
        parts.append("</body></html>")
        html = "".join(parts)
        return RenderedReport("text/html", f"{report.run_id}.html", html.encode())


def _section(title: str, body: str) -> str:
    return f"<section><h2>{escape(title)}</h2>{body}</section>"


def _header(header: dict) -> str:
    rows = "".join(f"<tr><th>{escape(str(key))}</th><td>{escape(_text(value))}</td></tr>" for key, value in header.items())
    return f"<table>{rows}</table>"


def _metrics(rows: list) -> str:
    body = "".join(
        "<tr>"
        f"<td>{escape(str(row.get('id')))}</td>"
        f"<td>{escape(_text(row.get('value')))}</td>"
        f"<td>{escape(_text(row.get('numerator')))}</td>"
        f"<td>{escape(_text(row.get('denominator')))}</td>"
        "</tr>"
        for row in rows
    )
    return "<table><tr><th>Metric</th><th>Value</th><th>Numerator</th><th>Denominator</th></tr>" + body + "</table>"


def _skipped(groups: list) -> str:
    if not groups:
        return "<p>Everything requested could be measured.</p>"
    items = "".join(f"<li>{escape(str(group.get('reason')))}: {escape(str(group.get('count')))}</li>" for group in groups)
    return f"<ul>{items}</ul>"


def _causes(causes: dict) -> str:
    rows = "".join(f"<tr><td>{escape(str(key))}</td><td>{escape(str(value))}</td></tr>" for key, value in causes.items())
    return f"<table><tr><th>Cause</th><th>Count</th></tr>{rows}</table>"


def _findings(findings: list) -> str:
    if not findings:
        return "<p>No findings.</p>"
    blocks = []
    for finding in findings:
        blocks.append(
            "<article>"
            f"<h3>{escape(str(finding.get('severity')))}: {escape(str(finding.get('cause')))}</h3>"
            f"<p>Count {escape(str(finding.get('count')))}.</p>"
            f"<p>{escape(str(finding.get('prose') or ''))}</p>"
            "</article>"
        )
    return "".join(blocks)


def _setup(rows: list) -> str:
    if not rows:
        return "<p>No setup changes.</p>"
    body = "".join(
        "<tr>"
        f"<td>{escape(str(row.get('setting')))}</td>"
        f"<td>{escape(str(row.get('current')))}</td>"
        f"<td>{escape(str(row.get('try')))}</td>"
        f"<td>{escape(str(row.get('why')))}</td>"
        "</tr>"
        for row in rows
    )
    return "<table><tr><th>Setting</th><th>Current</th><th>Try</th><th>Why</th></tr>" + body + "</table>"


def _compare(compare) -> str:
    if not compare:
        return "<p>No comparison selected.</p>"
    return f"<pre>{escape(_text(compare))}</pre>"


def _calibration(banner: dict) -> str:
    if not banner:
        return "<p>No calibration.</p>"
    return f"<p>{escape(str(banner.get('message') or ''))}</p>"


def _text(value) -> str:
    if isinstance(value, (dict, list)):
        import json

        return json.dumps(value, sort_keys=True)
    return "" if value is None else str(value)
