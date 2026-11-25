from app.domain.models import (
    Capabilities,
    Chunk,
    EvalContext,
    Trace,
    new_id,
)
from app.domain.models import TestCase as Case
from app.domain.text import jaccard, tokenize
from app.domain.verdicts import Claim, CorrectnessVerdict, FaithfulnessVerdict, KeyFact
from app.evaluators.base import NO_CLAIMS, NO_EXPECTED_ANSWER, NO_FACTS
from app.evaluators.chunking import ChunkMetrics, analyze_chunks
from app.evaluators.history import HistoryMetrics
from app.evaluators.quality import CorrectnessMetric, FaithfulnessMetric
from app.evaluators.retrieval import HitRateMetric, MrrMetric, PrecisionAtKMetric, RecallAtKMetric
from app.evaluators.runtime import RuntimeMetrics
from tests.fakes import FakeJudge

GOLD = "alpha beta gamma delta"
CHUNKS = [
    Chunk("c1", 1, "alpha beta gamma delta epsilon", 0.9, "doc", 1, None),
    Chunk("c2", 2, "alpha beta other words here now", 0.4, "doc", 1, None),
    Chunk("c3", 3, "totally unrelated text", 0.1, "doc", 1, None),
]


def _case(**overrides) -> Case:
    data = dict(
        id="case-1",
        dataset_id="ds",
        source_row=0,
        conversation_id=None,
        turn_index=0,
        question="What is the refund window?",
        expected_answer="30 days",
        gold_passage=GOLD,
    )
    data.update(overrides)
    return Case(**data)


def _trace(chunks=None, status="ok", answer="30 days") -> Trace:
    return Trace(
        id=new_id(),
        run_id="run-1",
        test_case_id="case-1",
        conversation_id=None,
        turn_index=0,
        kind="primary",
        repeat_index=0,
        question="What is the refund window?",
        answer=answer,
        rewritten_query=None,
        error=None if status == "ok" else "boom",
        latency_ms=12,
        prompt_tokens=8,
        completion_tokens=3,
        model="m",
        status=status,
        chunks=list(chunks or []),
    )


def _ctx(case=None, trace=None, judge=None, counter=None, **kwargs) -> EvalContext:
    context = EvalContext(
        test_case=case or _case(),
        primary=trace or _trace(CHUNKS),
        counterfactual=counter,
        prior_turns=[],
        capabilities=Capabilities(True, True, False, True),
        top_k=4,
        score_run_id="run-1",
    )
    if judge is not None:
        context.hit_cache["__bound_judge"] = judge
    for key, value in kwargs.items():
        setattr(context, key, value)
    return context


def test_tokenizer_strips_edge_punctuation_and_casefolds():
    assert tokenize("Alpha, BETA!") == ["alpha", "beta"]


def test_jaccard_bands_match_the_worked_examples():
    assert jaccard(GOLD, CHUNKS[0].text) == 0.8
    gray = jaccard(GOLD, CHUNKS[1].text)
    assert 0.2 <= gray < 0.5
    assert jaccard(GOLD, CHUNKS[2].text) == 0


def test_retrieval_fixture_hits_once_in_the_gray_band():
    judge = FakeJudge()
    ctx = _ctx(judge=judge)
    metrics = [
        HitRateMetric(judge).run(ctx),
        MrrMetric(judge).run(ctx),
        PrecisionAtKMetric(judge).run(ctx),
        RecallAtKMetric(judge).run(ctx),
    ]
    by_id = {row[0].metric_id: row[0] for row in metrics}
    assert by_id["hit"].value == 1
    assert by_id["mrr"].value == 1
    assert by_id["precision_at_k"].value == 0.5
    assert by_id["recall_at_k"].value == 1
    assert judge.useful_calls == 1


def test_expected_answer_is_the_passage_when_the_file_has_no_gold():
    judge = FakeJudge()
    case = _case(gold_passage=None, expected_answer=GOLD)
    row = HitRateMetric(judge).run(_ctx(case=case, trace=_trace([CHUNKS[0]]), judge=judge))[0]
    assert row.status == "ok"
    assert row.value == 1
    assert judge.useful_calls == 0


def test_clear_jaccard_bands_do_not_call_the_judge():
    judge = FakeJudge()
    high = _ctx(judge=judge, trace=_trace([CHUNKS[0]]))
    low = _ctx(judge=judge, trace=_trace([CHUNKS[2]]))
    assert HitRateMetric(judge).run(high)[0].value == 1
    assert HitRateMetric(judge).run(low)[0].value == 0
    assert judge.useful_calls == 0


def test_empty_fact_list_is_a_skip_not_zero():
    judge = FakeJudge()
    judge.correctness = CorrectnessVerdict(key_facts=[])
    row = CorrectnessMetric(judge).run(_ctx())[0]
    assert row.status == "skipped"
    assert row.skip_reason == NO_FACTS
    assert row.value is None


def test_empty_claim_list_is_a_skip():
    judge = FakeJudge()
    judge.faithfulness = FaithfulnessVerdict(claims=[])
    row = FaithfulnessMetric(judge).run(_ctx())[0]
    assert row.skip_reason == NO_CLAIMS


def test_supported_claim_without_chunk_id_is_invalid():
    judge = FakeJudge()
    judge.faithfulness = FaithfulnessVerdict(claims=[Claim(claim="c", supported=True, chunk_id="", reason="")])
    row = FaithfulnessMetric(judge).run(_ctx())[0]
    assert row.status == "error"
    assert row.skip_reason == "judge output invalid"


def test_missing_expected_answer_skips_correctness():
    row = CorrectnessMetric(FakeJudge()).run(_ctx(case=_case(expected_answer=None)))[0]
    assert row.skip_reason == NO_EXPECTED_ANSWER


def test_failed_trace_is_excluded_from_the_score_denominator():
    judge = FakeJudge()
    judge.correctness = CorrectnessVerdict(key_facts=[KeyFact(fact="window", present=True, reason="stated")])
    ok = CorrectnessMetric(judge).run(_ctx())
    failed = _trace(status="error")
    runtime = RuntimeMetrics().aggregate(
        [],
        ok,
        {
            "run_id": "run-1",
            "traces": [_trace(CHUNKS), failed],
            "price_table": None,
            "judge_usage": [],
            "repeats": 1,
            "has_secondary": False,
            "capabilities": Capabilities(True, True, False, True),
        },
    )
    error_rate = next(row for row in runtime if row.metric_id == "error_rate")
    assert error_rate.value == 0.5
    assert ok[0].value == 1


def test_certain_split_does_not_call_confirm_and_uncertain_does():
    judge = FakeJudge()
    whole = analyze_chunks(GOLD, [Chunk("c", 1, GOLD, None, None, None, None)])
    assert whole["split"] is False
    assert whole["needs_confirm"] is False
    gold = "alpha beta gamma delta epsilon zeta eta theta"
    uncertain = ChunkMetrics(judge).run(
        _ctx(case=_case(gold_passage=gold), trace=_trace([Chunk("c", 1, "alpha beta gamma delta", None, None, None, None)]), judge=judge)
    )
    assert judge.split_calls == 1
    assert uncertain[0].status == "ok"


def test_history_failure_compares_stored_hits_and_first_turn_skips():
    judge = FakeJudge()
    primary = _trace([CHUNKS[2]])
    counter = _trace([CHUNKS[0]])
    counter.kind = "standalone_counterfactual"
    follow = _ctx(
        case=_case(turn_index=1, conversation_id="c1"),
        trace=primary,
        counter=counter,
        judge=judge,
    )
    row = HistoryMetrics(judge).run(follow)[0]
    assert row.value == 1
    assert row.details["counterfactual_hit"] == 1
    assert row.details["primary_hit"] == 0
    first = HistoryMetrics(judge).run(_ctx(judge=judge))[0]
    assert first.skip_reason == "not a follow-up"
