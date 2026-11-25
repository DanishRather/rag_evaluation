from __future__ import annotations

from app.domain.errors import JudgeOutputError
from app.evaluators.base import NO_CLAIMS, NO_FACTS, Evaluator


class CorrectnessMetric(Evaluator):
    id = "correctness"
    metric_ids = ("correctness",)
    requires = frozenset({"expected_answer"})

    def evaluate(self, ctx):
        verdict = self._judge.check_correctness(
            ctx.primary.question,
            ctx.test_case.expected_answer or "",
            ctx.primary.answer or "",
        )
        facts = list(verdict.key_facts)
        if not facts:
            return [self.skipped(ctx, "correctness", NO_FACTS)]
        present = sum(1 for fact in facts if fact.present)
        return [
            self.scored(
                ctx,
                "correctness",
                present / len(facts),
                {
                    "numerator": present,
                    "denominator": len(facts),
                    "facts": [fact.model_dump() for fact in facts],
                },
                self._provenance("correctness"),
            )
        ]


class FaithfulnessMetric(Evaluator):
    id = "faithfulness"
    metric_ids = ("faithfulness",)
    requires = frozenset({"chunks"})

    def evaluate(self, ctx):
        verdict = self._judge.check_faithfulness(ctx.primary.answer or "", ctx.primary.chunks)
        claims = list(verdict.claims)
        if any(claim.supported and not (claim.chunk_id or "").strip() for claim in claims):
            raise JudgeOutputError(verdict)
        if not claims:
            return [self.skipped(ctx, "faithfulness", NO_CLAIMS)]
        supported = sum(1 for claim in claims if claim.supported)
        return [
            self.scored(
                ctx,
                "faithfulness",
                supported / len(claims),
                {
                    "numerator": supported,
                    "denominator": len(claims),
                    "claims": [claim.model_dump() for claim in claims],
                },
                self._provenance("faithfulness"),
            )
        ]
