"""Pure diagnosis. First matching YAML rule wins. No model calls."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.domain.models import Finding, MetricResult, SetupRow, SystemProfile, TestCase

_DIR = Path(__file__).resolve().parent
_SIGNALS = ("correct", "faithful", "gold_retrieved", "split", "standalone_works")


@dataclass(frozen=True)
class Rule:
    id: str
    cause: str
    severity: str
    when: dict[str, Any]


def load_rules() -> tuple[int, list[Rule]]:
    raw = yaml.safe_load((_DIR / "rules.yml").read_text(encoding="utf-8"))
    rules = [
        Rule(
            id=item["id"],
            cause=item["cause"],
            severity=item["severity"],
            when=dict(item["when"]),
        )
        for item in raw["rules"]
    ]
    return int(raw["version"]), rules


def load_setup_rows() -> list[dict[str, Any]]:
    raw = yaml.safe_load((_DIR / "setup.yml").read_text(encoding="utf-8"))
    return list(raw["rows"])


def _bound_ok(expected: dict[str, Any], actual: float) -> bool:
    if "min" in expected and actual < float(expected["min"]):
        return False
    if "max" in expected and actual >= float(expected["max"]):
        return False
    return True


def rule_matches(when: dict[str, Any], signals: dict[str, Any]) -> bool:
    for key, expected in when.items():
        if expected == "n/a":
            continue
        actual = signals.get(key, "n/a")
        if actual == "n/a":
            return False
        if isinstance(expected, bool):
            if actual is not expected:
                return False
            continue
        if isinstance(expected, dict):
            if not isinstance(actual, (int, float)):
                return False
            if not _bound_ok(expected, float(actual)):
                return False
            continue
        if actual != expected:
            return False
    return True


def first_match(signals: dict[str, Any], rules: list[Rule]) -> Rule | None:
    for rule in rules:
        if rule_matches(rule.when, signals):
            return rule
    return None


def _primary(metrics: list[MetricResult], test_case_id: str, metric_id: str) -> MetricResult | None:
    rows = [
        row
        for row in metrics
        if row.test_case_id == test_case_id and row.metric_id == metric_id and row.judge_slot == "primary"
    ]
    if not rows:
        return None
    ok = [row for row in rows if row.status == "ok"]
    chosen = ok or rows
    return sorted(chosen, key=lambda row: row.repeat_index)[0]


def _number(row: MetricResult | None) -> float | str:
    if row is None or row.status != "ok" or row.value is None:
        return "n/a"
    return float(row.value)


def _flag(row: MetricResult | None, *, true_at: float = 1) -> bool | str:
    if row is None or row.status != "ok" or row.value is None:
        return "n/a"
    return float(row.value) >= true_at


def question_signals(metrics: list[MetricResult], test_case_id: str) -> dict[str, Any]:
    correctness = _primary(metrics, test_case_id, "correctness")
    faithfulness = _primary(metrics, test_case_id, "faithfulness")
    hit = _primary(metrics, test_case_id, "hit")
    split = _primary(metrics, test_case_id, "chunk_split")
    history = _primary(metrics, test_case_id, "history_failure")
    correct_value = _number(correctness)
    faithful_value = _number(faithfulness)
    signals: dict[str, Any] = {
        "correctness": correct_value,
        "faithfulness": faithful_value,
        "gold_retrieved": _flag(hit),
        "split": _flag(split),
        "standalone_works": "n/a",
        "correct": "n/a"
        if correct_value == "n/a"
        else bool(correct_value >= 0.8),
        "faithful": "n/a"
        if faithful_value == "n/a"
        else bool(faithful_value >= 0.8),
    }
    if history is not None and history.status == "ok":
        counterfactual_hit = (history.details or {}).get("counterfactual_hit")
        if counterfactual_hit is None:
            signals["standalone_works"] = "n/a"
        else:
            signals["standalone_works"] = bool(counterfactual_hit)
    elif history is not None and history.status != "ok":
        signals["standalone_works"] = "n/a"
    return signals


def evidence_bucket(value: Any) -> str:
    if value == "n/a":
        return "n/a"
    return "true" if bool(value) else "false"


def aggregate_findings(
    matched: list[tuple[TestCase, Rule, dict[str, Any]]],
    run_id: str,
    new_id,
) -> list[Finding]:
    grouped: dict[str, list[tuple[TestCase, Rule, dict[str, Any]]]] = {}
    order: list[str] = []
    for case, rule, signals in matched:
        if rule.id not in grouped:
            order.append(rule.id)
            grouped[rule.id] = []
        grouped[rule.id].append((case, rule, signals))
    findings: list[Finding] = []
    for rule_id in order:
        rows = grouped[rule_id]
        rows.sort(key=lambda item: item[0].source_row)
        rule = rows[0][1]
        evidence: dict[str, dict[str, int]] = {
            name: {"true": 0, "false": 0, "n/a": 0} for name in _SIGNALS
        }
        for _case, _rule, signals in rows:
            for name in _SIGNALS:
                evidence[name][evidence_bucket(signals.get(name, "n/a"))] += 1
        findings.append(
            Finding(
                id=new_id(),
                run_id=run_id,
                rule_id=rule.id,
                cause=rule.cause,
                severity=rule.severity,
                count=len(rows),
                example_question_ids=[case.id for case, _rule, _signals in rows[:5]],
                evidence=evidence,
            )
        )
    return findings


def setup_table(profile: SystemProfile, rows: list[dict[str, Any]] | None = None) -> list[SetupRow]:
    spec = rows if rows is not None else load_setup_rows()
    values = profile.placeholders()
    emitted: list[SetupRow] = []
    for row in spec:
        if not _setup_matches(row.get("when") or {}, profile):
            continue
        emitted.append(
            SetupRow(
                id=row["id"],
                setting=row["setting"],
                current=_fill(row["current"], values),
                try_this=_fill(row["try"], values),
                why=_fill(row["why"], values),
            )
        )
    return emitted


def _setup_matches(when: dict[str, Any], profile: SystemProfile) -> bool:
    if not when:
        return False
    if "finding" in when:
        if profile.finding_counts.get(str(when["finding"]), 0) <= 0:
            return False
    if "split_answer_rate" in when:
        expected = when["split_answer_rate"]
        actual = profile.split_answer_rate
        if actual is None or not isinstance(expected, dict):
            return False
        if not _bound_ok(expected, float(actual)):
            return False
    return True


def _fill(template: str, values: dict[str, str]) -> str:
    class _Missing(dict):
        def __missing__(self, key: str) -> str:
            return "n/a"

    return template.format_map(_Missing(values))
