from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1)


class ProjectResponse(BaseModel):
    id: str
    name: str
    created_at: str


class SystemCreate(BaseModel):
    name: str = Field(min_length=1)


class SystemResponse(BaseModel):
    id: str
    project_id: str
    name: str
    created_at: str


class JudgeDefaultsResponse(BaseModel):
    provider: Literal["openai_chat", "openai_responses"]
    model_id: str = ""


class JudgeBody(BaseModel):
    provider: Literal["openai_chat", "openai_responses"]
    model_id: str = ""
    temperature: float = 0
    secondary: "JudgeBody | None" = None

    @field_validator("temperature")
    @classmethod
    def temperature_is_fixed(cls, value: float) -> float:
        if value != 0:
            raise ValueError("temperature is fixed at 0")
        return 0


class SystemConfigCreate(BaseModel):
    adapter_type: str
    adapter_settings: dict[str, Any] = Field(default_factory=dict)
    profile_settings: dict[str, Any] = Field(default_factory=dict)
    auth_secret: str | None = None


class SystemConfigResponse(BaseModel):
    id: str
    system_id: str
    version: int
    adapter_type: str
    adapter_settings: dict[str, Any]
    profile_settings: dict[str, Any]
    secret_id: str | None = None


class ConnectionResponse(BaseModel):
    project_id: str
    project_name: str
    system_id: str
    system_name: str
    created_at: str
    config: SystemConfigResponse


class ProbeRequest(BaseModel):
    question: str = "ping"


class ProbeResponse(BaseModel):
    capabilities: dict[str, bool]
    observed: dict[str, bool]
    error: str | None = None
    answer: str | None = None


class DatasetResponse(BaseModel):
    id: str
    project_id: str
    name: str
    source_filename: str
    headers: list[str]
    column_map: dict[str, str]
    preview: list[dict[str, Any]]
    case_count: int
    needs_mapping: bool


class ColumnMapRequest(BaseModel):
    question: str
    expected_answer: str | None = None
    gold_passage: str | None = None
    conversation_id: str | None = None


class TestCaseResponse(BaseModel):
    id: str
    dataset_id: str
    source_row: int
    conversation_id: str | None
    turn_index: int
    question: str
    expected_answer: str | None
    gold_passage: str | None


class EstimateRequest(BaseModel):
    dataset_id: str
    system_config_version_id: str
    judge: JudgeBody
    repeats: int = 1


class EstimateResponse(BaseModel):
    target_calls: int
    counterfactual_calls: int
    judge_calls: dict[str, int]
    notes: list[str]


class RunCreate(BaseModel):
    project_id: str
    dataset_id: str
    system_config_version_id: str
    judge: JudgeBody
    repeats: int = 1
    max_concurrency: int = 4
    price_table: dict[str, Any] | None = None
    use_judge_cache: bool = False
    target_timeout_s: float = 60
    target_max_attempts: int = 3
    evaluator_ids: list[str] | None = None


class ReevaluateRequest(BaseModel):
    judge: JudgeBody | None = None
    repeats: int | None = None
    use_judge_cache: bool | None = None


class RunResponse(BaseModel):
    id: str
    project_id: str
    dataset_id: str
    system_config_version_id: str
    replay_of_run_id: str | None
    status: str
    repeats: int
    max_concurrency: int
    judge_config: dict[str, Any]
    evaluator_ids: list[str]
    use_judge_cache: bool
    created_at: str


class LiveItemResponse(BaseModel):
    position: int
    test_case_id: str
    source_row: int
    question: str
    conversation_id: str | None
    turn_index: int
    repeat_index: int
    state: Literal["queued", "calling", "judging", "done", "failed", "not_run", "stopped"]
    stage: str | None = None
    started_at: str | None = None
    stage_started_at: str | None = None
    finished_at: str | None = None
    attempt: int | None = None
    max_attempts: int
    last_error: str | None = None
    error: str | None = None
    cause: str | None = None
    latency_ms: float | None = None
    answer: str | None = None


class RunLiveResponse(BaseModel):
    run_id: str
    status: str
    message: str
    total: int
    done: int
    failed: int
    running: int
    waiting: int
    remaining: int
    max_concurrency: int
    target_timeout_s: float
    runs_ahead: int
    busy_run_ids: list[str]
    worker: dict[str, Any]
    items: list[LiveItemResponse]
    log: list[dict[str, Any]]


class TraceResponse(BaseModel):
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
    status: str
    latency_ms: float | None
    prompt_tokens: int | None
    completion_tokens: int | None
    model: str | None
    chunks: list[dict[str, Any]]


class MetricRowResponse(BaseModel):
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
    judge_slot: str


class MetricsResponse(BaseModel):
    rows: list[MetricRowResponse]
    summary: dict[str, Any]


class FindingResponse(BaseModel):
    id: str
    run_id: str
    rule_id: str
    cause: str
    severity: str
    count: int
    example_question_ids: list[str]
    evidence: dict[str, Any]


class CalibrationLabelCreate(BaseModel):
    labels: list[dict[str, Any]]


class CalibrationAgreementResponse(BaseModel):
    item_count: int
    kappa: float | None
    trusted: bool
    warn: bool
    message: str


JudgeBody.model_rebuild()
