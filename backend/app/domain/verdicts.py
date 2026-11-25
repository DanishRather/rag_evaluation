from pydantic import BaseModel, ConfigDict, Field


class _Schema(BaseModel):
    model_config = ConfigDict(extra="ignore")


class KeyFact(_Schema):
    fact: str
    present: bool
    reason: str = ""


class CorrectnessVerdict(_Schema):
    key_facts: list[KeyFact] = Field(default_factory=list)


class Claim(_Schema):
    claim: str
    supported: bool
    chunk_id: str = ""
    reason: str = ""


class FaithfulnessVerdict(_Schema):
    claims: list[Claim] = Field(default_factory=list)


class UsefulnessVerdict(_Schema):
    useful: bool
    reason: str = ""


class SplitVerdict(_Schema):
    split_across_chunks: bool
    mixed_topic: bool
    reason: str = ""


class RewriteVerdict(_Schema):
    standalone_question: str
    resolved_pronouns: bool
    reason: str = ""


class FindingNote(_Schema):
    finding_id: str
    prose: str


class ReportProse(_Schema):
    summary: str
    finding_notes: list[FindingNote] = Field(default_factory=list)
