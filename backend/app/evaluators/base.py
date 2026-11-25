from __future__ import annotations

from app.domain.errors import JudgeOutputError
from app.domain.models import EvalContext, JudgeProvenance, MetricResult, new_id

NO_EXPECTED_ANSWER = "no expected answer"
NO_GOLD_PASSAGE = "no gold passage"
NO_CHUNKS = "no chunks"
NOT_A_FOLLOW_UP = "not a follow-up"
NO_STANDALONE_TRACE = "no standalone trace"
NO_LATENCY = "no latency"
NO_TOKEN_USAGE = "no token usage"
NO_FACTS = "judge returned no facts"
NO_CLAIMS = "judge returned no claims"
JUDGE_INVALID = "judge output invalid"

_REQUIRE_REASONS = (
    ("expected_answer", NO_EXPECTED_ANSWER),
    ("gold_passage", NO_GOLD_PASSAGE),
    ("chunks", NO_CHUNKS),
    ("follow_up", NOT_A_FOLLOW_UP),
    ("counterfactual_trace", NO_STANDALONE_TRACE),
    ("latency", NO_LATENCY),
    ("token_usage", NO_TOKEN_USAGE),
)


def gold_text(ctx: EvalContext) -> str:
    """Passage to compare. A file with only an expected answer uses that text."""
    return ((ctx.test_case.gold_passage or ctx.test_case.expected_answer) or "").strip()


def missing_requirement(
    requires: frozenset[str], ctx: EvalContext, order: tuple[str, ...] | None = None
) -> str | None:
    present = {
        "expected_answer": bool((ctx.test_case.expected_answer or "").strip()),
        "gold_passage": bool(gold_text(ctx)),
        "chunks": bool(ctx.primary.chunks),
        "follow_up": ctx.test_case.turn_index > 0,
        "counterfactual_trace": ctx.counterfactual is not None and ctx.counterfactual.status == "ok",
        "latency": ctx.primary.latency_ms is not None,
        "token_usage": bool(ctx.capabilities.has_token_usage),
    }
    reasons = dict(_REQUIRE_REASONS)
    sequence = order or tuple(reasons)
    for token in sequence:
        if token in requires and not present.get(token, False):
            return reasons[token]
    return None


class Evaluator:
    id: str = ""
    metric_ids: tuple[str, ...] = ()
    requires: frozenset[str] = frozenset()
    require_order: tuple[str, ...] | None = None

    def __init__(self, judge=None) -> None:
        self._judge = judge

    def evaluate(self, ctx: EvalContext) -> list[MetricResult]:
        raise NotImplementedError

    def aggregate(self, contexts: list[EvalContext], case_metrics: list[MetricResult], extras: dict) -> list[MetricResult]:
        return []

    def run(self, ctx: EvalContext) -> list[MetricResult]:
        reason = missing_requirement(self.requires, ctx, self.require_order)
        if reason:
            return [self.skipped(ctx, metric_id, reason) for metric_id in self.metric_ids]
        try:
            return self.evaluate(ctx)
        except JudgeOutputError:
            return [self.errored(ctx, metric_id, JUDGE_INVALID) for metric_id in self.metric_ids]

    def skipped(self, ctx: EvalContext, metric_id: str, reason: str) -> MetricResult:
        return self._row(ctx, metric_id, None, "skipped", reason, {})

    def errored(self, ctx: EvalContext, metric_id: str, reason: str) -> MetricResult:
        return self._row(ctx, metric_id, None, "error", reason, {})

    def scored(
        self,
        ctx: EvalContext,
        metric_id: str,
        value: float,
        details: dict,
        provenance: JudgeProvenance | None = None,
    ) -> MetricResult:
        return self._row(ctx, metric_id, value, "ok", None, details, provenance)

    def run_level(
        self,
        run_id: str,
        metric_id: str,
        value: float | None,
        status: str,
        details: dict | None = None,
        skip_reason: str | None = None,
    ) -> MetricResult:
        return MetricResult(
            id=new_id(),
            run_id=run_id,
            test_case_id="",
            metric_id=metric_id,
            value=value,
            status=status,
            skip_reason=skip_reason,
            details=details or {},
            rubric_version=None,
            judge_model=None,
            temperature=None,
            judge_role=None,
            prompt_hash=None,
            repeat_index=0,
            judge_slot="primary",
        )

    def _row(
        self,
        ctx: EvalContext,
        metric_id: str,
        value: float | None,
        status: str,
        skip_reason: str | None,
        details: dict,
        provenance: JudgeProvenance | None = None,
    ) -> MetricResult:
        return MetricResult(
            id=new_id(),
            run_id=ctx.score_run_id or ctx.primary.run_id,
            test_case_id=ctx.test_case.id,
            metric_id=metric_id,
            value=value,
            status=status,
            skip_reason=skip_reason,
            details=details,
            rubric_version=None if provenance is None else provenance.rubric_version,
            judge_model=None if provenance is None else provenance.model_id,
            temperature=None if provenance is None else provenance.temperature,
            judge_role=None if provenance is None else provenance.judge_role,
            prompt_hash=None if provenance is None else provenance.prompt_hash,
            repeat_index=ctx.repeat_index,
            judge_slot=ctx.judge_slot,
        )

    def _provenance(self, agent: str) -> JudgeProvenance | None:
        if self._judge is None:
            return None
        return self._judge.provenance(agent)
