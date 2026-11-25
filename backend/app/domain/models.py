"""Stored entities and the values that move between services. No I/O."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def new_id() -> str:
    return str(uuid.uuid4())


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


@dataclass
class Capabilities:
    has_chunks: bool
    has_scores: bool
    has_rewritten_query: bool
    has_token_usage: bool

    def to_dict(self) -> dict[str, bool]:
        return {
            "has_chunks": self.has_chunks,
            "has_scores": self.has_scores,
            "has_rewritten_query": self.has_rewritten_query,
            "has_token_usage": self.has_token_usage,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Capabilities:
        data = data or {}
        return cls(
            has_chunks=bool(data.get("has_chunks")),
            has_scores=bool(data.get("has_scores")),
            has_rewritten_query=bool(data.get("has_rewritten_query")),
            has_token_usage=bool(data.get("has_token_usage")),
        )


@dataclass
class JudgeConfig:
    provider: str
    model_id: str
    temperature: float = 0
    secondary: JudgeConfig | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "provider": self.provider,
            "model_id": self.model_id,
            "temperature": 0,
        }
        if self.secondary is not None:
            payload["secondary"] = self.secondary.to_dict()
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JudgeConfig:
        secondary = data.get("secondary")
        return cls(
            provider=str(data["provider"]),
            model_id=str(data["model_id"]),
            temperature=0,
            secondary=cls.from_dict(secondary) if secondary else None,
        )


@dataclass
class JudgeProvenance:
    rubric_version: int
    model_id: str
    temperature: float
    prompt_hash: str
    judge_role: str
    judge_slot: str


@dataclass
class Chunk:
    chunk_key: str
    rank: int
    text: str
    score: float | None = None
    source: str | None = None
    page: int | None = None
    token_length: int | None = None


@dataclass
class QueryRequest:
    question: str
    history: list[dict[str, Any]] = field(default_factory=list)
    test_case_id: str = ""
    conversation_id: str | None = None
    turn_index: int = 0


@dataclass
class Trace:
    id: str
    run_id: str
    test_case_id: str
    conversation_id: str | None
    turn_index: int
    kind: str
    repeat_index: int
    question: str
    answer: str | None
    rewritten_query: str | None
    error: str | None
    latency_ms: float | None
    prompt_tokens: int | None
    completion_tokens: int | None
    model: str | None
    status: str
    chunks: list[Chunk] = field(default_factory=list)


@dataclass
class Project:
    id: str
    name: str
    created_at: str


@dataclass
class System:
    id: str
    project_id: str
    name: str
    created_at: str


@dataclass
class SystemConfig:
    id: str
    system_id: str
    version: int
    adapter_type: str
    adapter_settings: dict[str, Any]
    profile_settings: dict[str, Any]
    secret_id: str | None = None


@dataclass
class Secret:
    id: str
    project_id: str
    ciphertext: str
    nonce: str


@dataclass
class Dataset:
    id: str
    project_id: str
    name: str
    source_filename: str
    column_map: dict[str, str]
    headers: list[str]
    raw_rows: list[dict[str, Any]]
    created_at: str


@dataclass
class TestCase:
    id: str
    dataset_id: str
    source_row: int
    conversation_id: str | None
    turn_index: int
    question: str
    expected_answer: str | None
    gold_passage: str | None


@dataclass
class Run:
    id: str
    project_id: str
    dataset_id: str
    system_config_version_id: str
    replay_of_run_id: str | None
    judge_config: dict[str, Any]
    evaluator_ids: list[str]
    price_table: dict[str, Any] | None
    repeats: int
    max_concurrency: int
    status: str
    idempotency_key: str | None
    request_hash: str
    use_judge_cache: bool
    target_timeout_s: float
    target_max_attempts: int
    capabilities: dict[str, Any]
    created_at: str


@dataclass
class Job:
    id: str
    run_id: str
    status: str
    attempts: int
    locked_at: str | None
    created_at: str


@dataclass
class MetricResult:
    id: str
    run_id: str
    test_case_id: str
    metric_id: str
    value: float | None
    status: str
    skip_reason: str | None
    details: dict[str, Any]
    rubric_version: int | None
    judge_model: str | None
    temperature: float | None
    judge_role: str | None
    prompt_hash: str | None
    repeat_index: int
    judge_slot: str = "primary"


@dataclass
class Finding:
    id: str
    run_id: str
    rule_id: str
    cause: str
    severity: str
    count: int
    example_question_ids: list[str]
    evidence: dict[str, Any]


@dataclass
class Report:
    id: str
    run_id: str
    model: dict[str, Any]


@dataclass
class CalibrationLabel:
    id: str
    dataset_id: str
    test_case_id: str
    human_correct: bool


@dataclass
class ProgressEvent:
    id: str
    run_id: str
    seq: int
    kind: str
    message: str
    payload: dict[str, Any]


@dataclass
class WorkerState:
    embedded: bool = False
    alive: bool = False
    current_run_id: str | None = None
    heartbeat: str | None = None


@dataclass
class JudgeUsage:
    id: str
    run_id: str
    test_case_id: str
    agent: str
    judge_slot: str
    model_id: str
    input_tokens: int | None
    output_tokens: int | None
    cost: float | None
    duration: float | None
    cache_hit: bool


@dataclass
class JudgeVerdict:
    """One calculated judge result. The same prompt keeps this verdict."""

    id: str
    cache_key: str
    agent: str
    model_id: str
    judge_slot: str
    prompt_hash: str
    verdict: dict[str, Any]


@dataclass
class RewriteRecord:
    id: str
    run_id: str
    test_case_id: str
    repeat_index: int
    standalone_question: str
    resolved_pronouns: bool
    reason: str


@dataclass
class RenderedReport:
    media_type: str
    filename: str
    body: bytes


@dataclass
class EvalContext:
    test_case: TestCase
    primary: Trace
    counterfactual: Trace | None
    prior_turns: list[dict[str, Any]]
    capabilities: Capabilities
    top_k: int
    repeat_index: int = 0
    judge_role: str = "primary"
    judge_slot: str = "primary"
    score_run_id: str = ""
    rewrite: Any = None
    hit_cache: dict[Any, Any] = field(default_factory=dict)


@dataclass
class SystemProfile:
    embedding_model: str | None = None
    top_k: int | None = None
    chunk_size_tokens: int | None = None
    chunk_overlap_tokens: int | None = None
    llm: str | None = None
    prompts: Any = None
    mean_chunk_tokens: float | None = None
    neighbor_overlap: float | None = None
    median_chunk_count: float | None = None
    observed_model: str | None = None
    split_answer_rate: float | None = None
    hit: float | None = None
    history_failure_rate: float | None = None
    finding_counts: dict[str, int] = field(default_factory=dict)

    def placeholders(self) -> dict[str, str]:
        def num(value: float | None) -> str:
            if value is None:
                return "n/a"
            return f"{value:.2f}"

        prompts = self.prompts
        if isinstance(prompts, dict):
            prompts_text = json.dumps(prompts, sort_keys=True)
        else:
            prompts_text = "" if prompts is None else str(prompts)
        return {
            "embedding_model": self.embedding_model or "n/a",
            "top_k": "n/a" if self.top_k is None else str(self.top_k),
            "chunk_size_tokens": "n/a" if self.chunk_size_tokens is None else str(self.chunk_size_tokens),
            "chunk_overlap_tokens": "n/a"
            if self.chunk_overlap_tokens is None
            else str(self.chunk_overlap_tokens),
            "llm": self.llm or self.observed_model or "n/a",
            "prompts": prompts_text or "n/a",
            "mean_chunk_tokens": num(self.mean_chunk_tokens),
            "neighbor_overlap": num(self.neighbor_overlap),
            "median_chunk_count": num(self.median_chunk_count),
            "observed_model": self.observed_model or "n/a",
            "split_answer_rate": num(self.split_answer_rate),
            "hit": num(self.hit),
            "history_failure_rate": num(self.history_failure_rate),
        }


@dataclass
class AdapterBuild:
    settings: dict[str, Any]
    secret: Secret | None
    timeout_s: float


@dataclass
class RunSpec:
    project_id: str
    dataset_id: str
    system_config_version_id: str
    judge: JudgeConfig
    repeats: int = 1
    max_concurrency: int = 4
    price_table: dict[str, Any] | None = None
    use_judge_cache: bool = False
    target_timeout_s: float = 60
    target_max_attempts: int = 3
    evaluator_ids: list[str] | None = None

    def hash_payload(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "dataset_id": self.dataset_id,
            "system_config_version_id": self.system_config_version_id,
            "judge": self.judge.to_dict(),
            "repeats": self.repeats,
            "max_concurrency": self.max_concurrency,
            "price_table": self.price_table,
            "use_judge_cache": self.use_judge_cache,
            "target_timeout_s": self.target_timeout_s,
            "target_max_attempts": self.target_max_attempts,
            "evaluator_ids": self.evaluator_ids,
        }


@dataclass
class Estimate:
    target_calls: int
    counterfactual_calls: int
    judge_calls: dict[str, int]
    notes: list[str]


@dataclass
class DatasetView:
    dataset: Dataset
    preview: list[dict[str, Any]]
    case_count: int
    needs_mapping: bool


@dataclass
class ProbeResult:
    capabilities: Capabilities
    observed: dict[str, bool]
    error: str | None = None
    answer: str | None = None


@dataclass
class DiagnosisOutcome:
    findings: list[Finding]
    unclassified: int
    target_failures: int
    per_question: list[dict[str, Any]]


@dataclass
class SetupRow:
    id: str
    setting: str
    current: str
    try_this: str
    why: str


@dataclass
class CalibrationAgreement:
    item_count: int
    kappa: float | None
    trusted: bool
    warn: bool
    message: str
