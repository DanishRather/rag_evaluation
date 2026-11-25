from __future__ import annotations

from app.evaluators.base import Evaluator
from app.evaluators.hits import decide_hits


class HistoryMetrics(Evaluator):
    id = "history_failure"
    metric_ids = ("history_failure",)
    requires = frozenset({"follow_up", "counterfactual_trace", "gold_passage"})
    require_order = ("follow_up", "counterfactual_trace", "gold_passage")

    def evaluate(self, ctx):
        if ctx.hit_cache.get("__bound_judge") is None:
            ctx.hit_cache["__bound_judge"] = self._judge
        primary_flags = decide_hits(ctx, ctx.primary.chunks, cache_prefix="primary")
        assert ctx.counterfactual is not None
        counter_flags = decide_hits(
            ctx,
            ctx.counterfactual.chunks,
            cache_prefix="counterfactual",
            question=ctx.counterfactual.question,
        )
        primary_hit = 1 if any(primary_flags) else 0
        counter_hit = 1 if any(counter_flags) else 0
        failed = 1.0 if counter_hit == 1 and primary_hit == 0 else 0.0
        resolved = None
        if ctx.rewrite is not None:
            resolved = bool(ctx.rewrite.resolved_pronouns)
        return [
            self.scored(
                ctx,
                "history_failure",
                failed,
                {
                    "numerator": failed,
                    "denominator": 1,
                    "primary_hit": primary_hit,
                    "counterfactual_hit": counter_hit,
                    "resolved_pronouns": resolved,
                    "standalone_question": None if ctx.rewrite is None else ctx.rewrite.standalone_question,
                },
            )
        ]

    def aggregate(self, contexts, case_metrics, extras):
        run_id = extras["run_id"]
        rows = [
            row
            for row in case_metrics
            if row.metric_id == "history_failure" and row.judge_slot == "primary" and row.status == "ok"
        ]
        if not rows:
            return [
                self.run_level(
                    run_id,
                    "history_failure_rate",
                    None,
                    "skipped",
                    skip_reason="No follow-up was scored",
                )
            ]
        failures = sum(1 for row in rows if (row.value or 0) >= 1)
        resolved_values = [
            1.0 if row.details.get("resolved_pronouns") else 0.0
            for row in rows
            if row.details.get("resolved_pronouns") is not None
        ]
        counter_hits = sum(1 for row in rows if row.details.get("counterfactual_hit"))
        details = {
            "numerator": failures,
            "denominator": len(rows),
            "history_failure_count": failures,
            "pronoun_resolution_rate": None
            if not resolved_values
            else sum(resolved_values) / len(resolved_values),
            "rewrite_quality": counter_hits / len(rows),
            "scored_followups": len(rows),
        }
        return [self.run_level(run_id, "history_failure_rate", failures / len(rows), "ok", details)]
