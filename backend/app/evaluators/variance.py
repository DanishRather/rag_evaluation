from __future__ import annotations

from collections import defaultdict

from app.evaluators.base import Evaluator

_CASE_METRICS = (
    "correctness",
    "faithfulness",
    "hit",
    "mrr",
    "precision_at_k",
    "recall_at_k",
    "chunk_split",
    "history_failure",
)


def sample_variance(values: list[float]) -> float:
    count = len(values)
    center = sum(values) / count
    return sum((value - center) ** 2 for value in values) / (count - 1)


class VarianceMetrics(Evaluator):
    id = "variance"
    metric_ids = ()
    requires = frozenset()

    def evaluate(self, ctx):
        return []

    def aggregate(self, contexts, case_metrics, extras):
        run_id = extras["run_id"]
        repeats = int(extras.get("repeats") or 1)
        results = []
        if repeats == 1:
            results.append(
                self.run_level(run_id, "judge_variance", None, "skipped", skip_reason="repeats == 1")
            )
        else:
            grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
            for row in case_metrics:
                if row.status != "ok" or row.value is None or row.judge_slot != "primary":
                    continue
                if row.metric_id not in _CASE_METRICS or row.test_case_id == "":
                    continue
                grouped[(row.test_case_id, row.metric_id)].append(float(row.value))
            variances = [sample_variance(values) for values in grouped.values() if len(values) >= 2]
            if variances:
                results.append(
                    self.run_level(
                        run_id,
                        "judge_variance",
                        sum(variances) / len(variances),
                        "ok",
                        {"numerator": sum(variances), "denominator": len(variances)},
                    )
                )
            else:
                results.append(
                    self.run_level(run_id, "judge_variance", None, "skipped", skip_reason="repeats == 1")
                )
        if not extras.get("has_secondary"):
            results.append(
                self.run_level(
                    run_id,
                    "judge_disagreement",
                    None,
                    "skipped",
                    skip_reason="No secondary judge",
                )
            )
            return results
        primary: dict[tuple[str, str, int], float] = {}
        secondary: dict[tuple[str, str, int], float] = {}
        for row in case_metrics:
            if row.status != "ok" or row.value is None or row.test_case_id == "":
                continue
            if row.metric_id not in _CASE_METRICS:
                continue
            key = (row.test_case_id, row.metric_id, row.repeat_index)
            if row.judge_slot == "primary":
                primary[key] = float(row.value)
            elif row.judge_slot == "secondary":
                secondary[key] = float(row.value)
        shared = [abs(primary[key] - secondary[key]) for key in primary if key in secondary]
        if not shared:
            results.append(
                self.run_level(
                    run_id,
                    "judge_disagreement",
                    None,
                    "skipped",
                    skip_reason="No secondary judge",
                )
            )
        else:
            results.append(
                self.run_level(
                    run_id,
                    "judge_disagreement",
                    sum(shared) / len(shared),
                    "ok",
                    {"numerator": sum(shared), "denominator": len(shared)},
                )
            )
        return results
