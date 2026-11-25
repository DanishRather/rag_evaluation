from typing import Protocol

from app.domain.models import Chunk, Finding, JudgeConfig, JudgeProvenance
from app.domain.verdicts import (
    CorrectnessVerdict,
    FaithfulnessVerdict,
    ReportProse,
    RewriteVerdict,
    SplitVerdict,
    UsefulnessVerdict,
)


class Judge(Protocol):
    def prepare(
        self,
        config: JudgeConfig,
        *,
        repeats: int,
        use_judge_cache: bool,
        role: str,
        run_id: str,
    ) -> None: ...

    def provenance(self, agent: str) -> JudgeProvenance: ...

    def check_correctness(
        self, question: str, expected_answer: str, actual_answer: str
    ) -> CorrectnessVerdict: ...

    def check_faithfulness(self, actual_answer: str, chunks: list[Chunk]) -> FaithfulnessVerdict: ...

    def check_chunk_usefulness(
        self, question: str, gold_passage: str, chunk: Chunk
    ) -> UsefulnessVerdict: ...

    def confirm_chunk_split(self, gold_passage: str, neighbors: list[Chunk]) -> SplitVerdict: ...

    def rewrite_standalone(self, history: list[dict], follow_up: str) -> RewriteVerdict: ...

    def write_report(self, findings: list[Finding]) -> ReportProse: ...
