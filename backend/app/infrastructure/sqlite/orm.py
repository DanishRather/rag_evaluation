from sqlalchemy import Float, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ProjectRow(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)


class SystemRow(Base):
    __tablename__ = "systems"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)


class SystemConfigRow(Base):
    __tablename__ = "system_configs"
    __table_args__ = (UniqueConstraint("system_id", "version"),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    system_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    adapter_type: Mapped[str] = mapped_column(String, nullable=False)
    adapter_settings_json: Mapped[str] = mapped_column(Text, nullable=False)
    profile_settings_json: Mapped[str] = mapped_column(Text, nullable=False)
    secret_id: Mapped[str | None] = mapped_column(String)


class SecretRow(Base):
    __tablename__ = "secrets"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    nonce: Mapped[str] = mapped_column(String, nullable=False)


class DatasetRow(Base):
    __tablename__ = "datasets"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    source_filename: Mapped[str] = mapped_column(String, nullable=False)
    column_map_json: Mapped[str] = mapped_column(Text, nullable=False)
    headers_json: Mapped[str] = mapped_column(Text, nullable=False)
    raw_rows_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)


class TestCaseRow(Base):
    __tablename__ = "test_cases"
    __table_args__ = (
        UniqueConstraint("dataset_id", "source_row"),
        Index("ix_cases_dataset_conversation", "dataset_id", "conversation_id"),
    )
    id: Mapped[str] = mapped_column(String, primary_key=True)
    dataset_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    source_row: Mapped[int] = mapped_column(Integer, nullable=False)
    conversation_id: Mapped[str | None] = mapped_column(String)
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    expected_answer: Mapped[str | None] = mapped_column(Text)
    gold_passage: Mapped[str | None] = mapped_column(Text)


class RunRow(Base):
    __tablename__ = "runs"
    __table_args__ = (UniqueConstraint("idempotency_key"),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    dataset_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    system_config_version_id: Mapped[str] = mapped_column(String, nullable=False)
    replay_of_run_id: Mapped[str | None] = mapped_column(String)
    judge_config_json: Mapped[str] = mapped_column(Text, nullable=False)
    evaluator_ids_json: Mapped[str] = mapped_column(Text, nullable=False)
    price_table_json: Mapped[str | None] = mapped_column(Text)
    repeats: Mapped[int] = mapped_column(Integer, nullable=False)
    max_concurrency: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String)
    request_hash: Mapped[str] = mapped_column(String, nullable=False)
    use_judge_cache: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    target_timeout_s: Mapped[float] = mapped_column(Float, nullable=False)
    target_max_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    capabilities_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)


class JobRow(Base):
    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("run_id"), Index("ix_jobs_status", "status"))
    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_at: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String, nullable=False)


class TraceRow(Base):
    __tablename__ = "traces"
    __table_args__ = (
        UniqueConstraint("run_id", "test_case_id", "kind", "repeat_index"),
        Index("ix_traces_run_id", "run_id"),
    )
    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(String, nullable=False)
    test_case_id: Mapped[str] = mapped_column(String, nullable=False)
    conversation_id: Mapped[str | None] = mapped_column(String)
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    repeat_index: Mapped[int] = mapped_column(Integer, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str | None] = mapped_column(Text)
    rewritten_query: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[float | None] = mapped_column(Float)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    model: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, nullable=False)


class TraceChunkRow(Base):
    __tablename__ = "trace_chunks"
    __table_args__ = (UniqueConstraint("trace_id", "rank"),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    trace_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_key: Mapped[str] = mapped_column(String, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str | None] = mapped_column(String)
    page: Mapped[int | None] = mapped_column(Integer)
    token_length: Mapped[int | None] = mapped_column(Integer)


class MetricResultRow(Base):
    __tablename__ = "metric_results"
    __table_args__ = (
        UniqueConstraint("run_id", "test_case_id", "metric_id", "repeat_index", "judge_slot"),
    )
    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    test_case_id: Mapped[str] = mapped_column(String, nullable=False)
    metric_id: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String, nullable=False)
    skip_reason: Mapped[str | None] = mapped_column(String)
    details_json: Mapped[str] = mapped_column(Text, nullable=False)
    rubric_version: Mapped[int | None] = mapped_column(Integer)
    judge_model: Mapped[str | None] = mapped_column(String)
    temperature: Mapped[float | None] = mapped_column(Float)
    judge_role: Mapped[str | None] = mapped_column(String)
    prompt_hash: Mapped[str | None] = mapped_column(String)
    repeat_index: Mapped[int] = mapped_column(Integer, nullable=False)
    judge_slot: Mapped[str] = mapped_column(String, nullable=False)


class FindingRow(Base):
    __tablename__ = "findings"
    __table_args__ = (UniqueConstraint("run_id", "rule_id"),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    rule_id: Mapped[str] = mapped_column(String, nullable=False)
    cause: Mapped[str] = mapped_column(String, nullable=False)
    severity: Mapped[str] = mapped_column(String, nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False)
    example_question_ids_json: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False)


class ReportRow(Base):
    __tablename__ = "reports"
    __table_args__ = (UniqueConstraint("run_id"),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(String, nullable=False)
    model_json: Mapped[str] = mapped_column(Text, nullable=False)


class CalibrationLabelRow(Base):
    __tablename__ = "calibration_labels"
    __table_args__ = (UniqueConstraint("dataset_id", "test_case_id"),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    dataset_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    test_case_id: Mapped[str] = mapped_column(String, nullable=False)
    human_correct: Mapped[int] = mapped_column(Integer, nullable=False)


class ProgressEventRow(Base):
    __tablename__ = "progress_events"
    __table_args__ = (
        UniqueConstraint("run_id", "seq"),
        Index("ix_progress_run_seq", "run_id", "seq"),
    )
    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(String, nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)


class JudgeVerdictRow(Base):
    __tablename__ = "judge_verdicts"
    __table_args__ = (UniqueConstraint("cache_key"),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    cache_key: Mapped[str] = mapped_column(String, nullable=False)
    agent: Mapped[str] = mapped_column(String, nullable=False)
    model_id: Mapped[str] = mapped_column(String, nullable=False)
    judge_slot: Mapped[str] = mapped_column(String, nullable=False)
    prompt_hash: Mapped[str] = mapped_column(String, nullable=False)
    verdict_json: Mapped[str] = mapped_column(Text, nullable=False)


class JudgeUsageRow(Base):
    __tablename__ = "judge_usage"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    test_case_id: Mapped[str] = mapped_column(String, nullable=False)
    agent: Mapped[str] = mapped_column(String, nullable=False)
    judge_slot: Mapped[str] = mapped_column(String, nullable=False)
    model_id: Mapped[str] = mapped_column(String, nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cost: Mapped[float | None] = mapped_column(Float)
    duration: Mapped[float | None] = mapped_column(Float)
    cache_hit: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class RewriteRecordRow(Base):
    __tablename__ = "rewrite_records"
    __table_args__ = (UniqueConstraint("run_id", "test_case_id", "repeat_index"),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    test_case_id: Mapped[str] = mapped_column(String, nullable=False)
    repeat_index: Mapped[int] = mapped_column(Integer, nullable=False)
    standalone_question: Mapped[str] = mapped_column(Text, nullable=False)
    resolved_pronouns: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
