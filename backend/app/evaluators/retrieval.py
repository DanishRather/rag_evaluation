from __future__ import annotations

from app.evaluators.base import Evaluator
from app.evaluators.hits import decide_hits, first_hit_rank


class _Retrieval(Evaluator):
    requires = frozenset({"gold_passage"})

    def _flags(self, ctx):
        if ctx.hit_cache.get("__bound_judge") is None:
            ctx.hit_cache["__bound_judge"] = self._judge
        return decide_hits(ctx, ctx.primary.chunks)


class HitRateMetric(_Retrieval):
    id = "hit"
    metric_ids = ("hit",)

    def evaluate(self, ctx):
        flags = self._flags(ctx)
        hit = 1.0 if any(flags) else 0.0
        return [
            self.scored(
                ctx,
                "hit",
                hit,
                {"numerator": hit, "denominator": 1, "flags": flags, "k": ctx.top_k},
                self._provenance("usefulness"),
            )
        ]


class MrrMetric(_Retrieval):
    id = "mrr"
    metric_ids = ("mrr",)

    def evaluate(self, ctx):
        flags = self._flags(ctx)
        rank = first_hit_rank(ctx.primary.chunks, flags)
        value = 0.0 if rank is None else 1.0 / rank
        return [
            self.scored(
                ctx,
                "mrr",
                value,
                {"numerator": 0 if rank is None else 1, "denominator": rank or 0, "rank": rank},
                self._provenance("usefulness"),
            )
        ]


class PrecisionAtKMetric(_Retrieval):
    id = "precision_at_k"
    metric_ids = ("precision_at_k",)

    def evaluate(self, ctx):
        flags = self._flags(ctx)
        k = max(int(ctx.top_k), 1)
        useful = sum(1 for flag in flags if flag)
        return [
            self.scored(
                ctx,
                "precision_at_k",
                useful / k,
                {"numerator": useful, "denominator": k, "flags": flags},
                self._provenance("usefulness"),
            )
        ]


class RecallAtKMetric(_Retrieval):
    id = "recall_at_k"
    metric_ids = ("recall_at_k",)

    def evaluate(self, ctx):
        flags = self._flags(ctx)
        value = 1.0 if any(flags) else 0.0
        return [
            self.scored(
                ctx,
                "recall_at_k",
                value,
                {"numerator": value, "denominator": 1},
                self._provenance("usefulness"),
            )
        ]
