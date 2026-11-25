"""Read stored metric rows into the summary the API returns."""

from __future__ import annotations

from collections import Counter

from app.domain.models import MetricResult


def summarize(metrics: list[MetricResult]) -> dict:
    primary = [row for row in metrics if row.judge_slot == "primary"]
    run_level = {
        row.metric_id: row
        for row in primary
        if row.test_case_id == "" and row.status == "ok"
    }
    case_groups: dict[str, list[MetricResult]] = {}
    for row in primary:
        if row.test_case_id == "" or row.status != "ok" or row.value is None:
            continue
        case_groups.setdefault(row.metric_id, []).append(row)
    summary: dict[str, dict] = {}
    metric_ids = set(run_level) | set(case_groups) | {row.metric_id for row in primary}
    for metric_id in sorted(metric_ids):
        stored = run_level.get(metric_id)
        if stored is not None:
            summary[metric_id] = {
                "value": stored.value,
                "numerator": (stored.details or {}).get("numerator"),
                "denominator": (stored.details or {}).get("denominator"),
                "status": stored.status,
                "details": stored.details or {},
            }
            continue
        rows = case_groups.get(metric_id) or []
        if not rows:
            skipped = [row for row in primary if row.metric_id == metric_id and row.status != "ok"]
            summary[metric_id] = {
                "value": None,
                "numerator": None,
                "denominator": None,
                "status": skipped[0].status if skipped else "skipped",
                "details": {"skip_reason": skipped[0].skip_reason if skipped else None},
            }
            continue
        value = sum(float(row.value or 0) for row in rows) / len(rows)
        summary[metric_id] = {
            "value": value,
            "numerator": sum(float((row.details or {}).get("numerator") or 0) for row in rows),
            "denominator": sum(float((row.details or {}).get("denominator") or 0) for row in rows),
            "status": "ok",
            "details": {},
        }
    histogram = []
    avg = run_level.get("avg_chunk_tokens")
    if avg is not None:
        histogram = list((avg.details or {}).get("histogram") or [])
    skipped_counts = Counter(row.skip_reason for row in primary if row.status == "skipped" and row.skip_reason)
    history = run_level.get("history_failure_rate")
    history_block = {} if history is None else dict(history.details or {})
    return {
        "metrics": summary,
        "histogram": histogram,
        "skipped": [{"reason": reason, "count": count} for reason, count in sorted(skipped_counts.items())],
        "history": history_block,
    }
