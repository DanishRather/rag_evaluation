from app.domain.models import Capabilities, QueryRequest, Trace, new_id
from app.domain.verdicts import (
    CorrectnessVerdict,
    FaithfulnessVerdict,
    FindingNote,
    KeyFact,
    ReportProse,
    RewriteVerdict,
    SplitVerdict,
    UsefulnessVerdict,
)


class FakeJudge:
    def __init__(self) -> None:
        self.useful_calls = 0
        self.rewrite_calls = 0
        self.split_calls = 0
        self.prepared = None
        self.correctness = CorrectnessVerdict(key_facts=[KeyFact(fact="fact", present=True, reason="yes")])
        self.faithfulness = FaithfulnessVerdict(
            claims=[{"claim": "c", "supported": True, "chunk_id": "c1", "reason": "quoted"}]
        )
        self.useful = UsefulnessVerdict(useful=True, reason="overlap")
        self.split = SplitVerdict(split_across_chunks=True, mixed_topic=False, reason="cut")
        self.rewrite = RewriteVerdict(standalone_question="standalone question", resolved_pronouns=True, reason="resolved")

    def prepare(self, config, *, repeats, use_judge_cache, role, run_id) -> None:
        self.prepared = (config, repeats, use_judge_cache, role, run_id)

    def provenance(self, agent: str):
        from app.domain.models import JudgeProvenance

        return JudgeProvenance(1, "fake-model", 0, "hash", agent, "primary" if self.prepared is None else self.prepared[3])

    def check_correctness(self, question, expected_answer, actual_answer):
        return self.correctness

    def check_faithfulness(self, actual_answer, chunks):
        return self.faithfulness

    def check_chunk_usefulness(self, question, gold_passage, chunk):
        self.useful_calls += 1
        return self.useful

    def confirm_chunk_split(self, gold_passage, neighbors):
        self.split_calls += 1
        return self.split

    def rewrite_standalone(self, history, follow_up):
        self.rewrite_calls += 1
        return self.rewrite

    def write_report(self, findings):
        notes = [FindingNote(finding_id=finding.id, prose=f"Note {finding.cause}") for finding in findings]
        notes.append(FindingNote(finding_id="not-a-real-finding", prose="invented"))
        return ReportProse(summary="Report summary", finding_notes=notes)


class ScriptAdapter:
    def __init__(self, handler=None, capabilities=None) -> None:
        self.handler = handler
        self.calls: list[QueryRequest] = []
        self._capabilities = capabilities or Capabilities(True, True, True, True)

    def capabilities(self) -> Capabilities:
        return self._capabilities

    def run_query(self, request: QueryRequest) -> Trace:
        self.calls.append(request)
        if self.handler is None:
            return _ok_trace(request, "answer", [])
        return self.handler(request)


def _ok_trace(request: QueryRequest, answer: str, chunks) -> Trace:
    return Trace(
        id=new_id(),
        run_id="",
        test_case_id=request.test_case_id,
        conversation_id=request.conversation_id,
        turn_index=request.turn_index,
        kind="primary",
        repeat_index=0,
        question=request.question,
        answer=answer,
        rewritten_query=None,
        error=None,
        latency_ms=10,
        prompt_tokens=5,
        completion_tokens=2,
        model="target-model",
        status="ok",
        chunks=list(chunks),
    )
