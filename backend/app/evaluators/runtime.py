from __future__ import annotations

import math

from app.evaluators.base import NO_LATENCY, NO_TOKEN_USAGE, Evaluator


def nearest_rank(values: list[float], percent: float) -> float:
    ordered = sorted(values)
    rank = math.ceil(percent / 100 * len(ordered))
    index = min(len(ordered), max(rank, 1)) - 1
    return float(ordered[index])


class RuntimeMetrics(Evaluator):
    id = "runtime"
    metric_ids = ()
    requires = frozenset()

    def evaluate(self, ctx):
        return []

    def aggregate(self, contexts, case_metrics, extras):
        run_id = extras["run_id"]
        traces = list(extras.get("traces") or [])
        if not traces:
            return [self.run_level(run_id, "error_rate", None, "skipped", skip_reason="No traces")]
        errors = sum(1 for trace in traces if trace.status == "error")
        results = [
            self.run_level(
                run_id,
                "error_rate",
                errors / len(traces),
                "ok",
                {"numerator": errors, "denominator": len(traces)},
            )
        ]
        latencies = [
            float(trace.latency_ms)
            for trace in traces
            if trace.status == "ok" and trace.kind == "primary" and trace.latency_ms is not None
        ]
        if latencies:
            results.append(
                self.run_level(run_id, "latency_p50", nearest_rank(latencies, 50), "ok", {"n": len(latencies)})
            )
            results.append(
                self.run_level(run_id, "latency_p95", nearest_rank(latencies, 95), "ok", {"n": len(latencies)})
            )
        else:
            results.append(self.run_level(run_id, "latency_p50", None, "skipped", skip_reason=NO_LATENCY))
            results.append(self.run_level(run_id, "latency_p95", None, "skipped", skip_reason=NO_LATENCY))

        ok_traces = [trace for trace in traces if trace.status == "ok"]
        has_usage = any(
            trace.prompt_tokens is not None or trace.completion_tokens is not None for trace in ok_traces
        )
        capabilities = extras.get("capabilities")
        usage_disabled = capabilities is not None and not capabilities.has_token_usage and not has_usage
        if usage_disabled or not has_usage:
            results.append(self.run_level(run_id, "prompt_tokens", None, "skipped", skip_reason=NO_TOKEN_USAGE))
            results.append(
                self.run_level(run_id, "completion_tokens", None, "skipped", skip_reason=NO_TOKEN_USAGE)
            )
        else:
            prompt = sum(trace.prompt_tokens or 0 for trace in ok_traces)
            completion = sum(trace.completion_tokens or 0 for trace in ok_traces)
            by_model: dict[str, dict[str, int]] = {}
            for trace in ok_traces:
                bucket = by_model.setdefault(trace.model or "", {"prompt": 0, "completion": 0})
                bucket["prompt"] += trace.prompt_tokens or 0
                bucket["completion"] += trace.completion_tokens or 0
            results.append(
                self.run_level(run_id, "prompt_tokens", float(prompt), "ok", {"numerator": prompt, "denominator": 1})
            )
            results.append(
                self.run_level(
                    run_id,
                    "completion_tokens",
                    float(completion),
                    "ok",
                    {"numerator": completion, "denominator": 1, "by_model": by_model},
                )
            )
            price_table = extras.get("price_table") or None
            if price_table:
                cost, priced, missing = _target_cost(by_model, price_table)
                results.append(
                    self.run_level(
                        run_id,
                        "target_cost",
                        cost,
                        "ok",
                        {"priced_models": priced, "unpriced_models": missing},
                    )
                )

        usage_rows = list(extras.get("judge_usage") or [])
        if usage_rows:
            prompt_tokens = sum(row.input_tokens or 0 for row in usage_rows)
            output_tokens = sum(row.output_tokens or 0 for row in usage_rows)
            results.append(
                self.run_level(run_id, "judge_prompt_tokens", float(prompt_tokens), "ok", {"numerator": prompt_tokens})
            )
            results.append(
                self.run_level(
                    run_id, "judge_completion_tokens", float(output_tokens), "ok", {"numerator": output_tokens}
                )
            )
            costs = [row.cost for row in usage_rows if row.cost is not None]
            if costs:
                results.append(
                    self.run_level(run_id, "judge_cost", float(sum(costs)), "ok", {"calls": len(usage_rows)})
                )
        return results


def _target_cost(by_model: dict, price_table: dict) -> tuple[float, list[str], list[str]]:
    total = 0.0
    priced: list[str] = []
    missing: list[str] = []
    for model_id, tokens in by_model.items():
        price = price_table.get(model_id)
        if not price:
            if model_id:
                missing.append(model_id)
            continue
        total += tokens["prompt"] / 1_000_000 * float(price["input_per_million"])
        total += tokens["completion"] / 1_000_000 * float(price["output_per_million"])
        priced.append(model_id)
    return total, priced, missing
