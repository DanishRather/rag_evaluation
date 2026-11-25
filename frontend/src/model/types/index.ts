export type ThemeMode = "system" | "light" | "dark";
export type ResultsTab = "questions" | "retrieval" | "chunking" | "history" | "model";

export interface Project {
  id: string;
  name: string;
  created_at: string;
}

export interface SystemRecord {
  id: string;
  project_id: string;
  name: string;
  created_at: string;
}

export interface SystemConfig {
  id: string;
  system_id: string;
  version: number;
  adapter_type: string;
  adapter_settings: Record<string, unknown>;
  profile_settings: Record<string, unknown>;
  secret_id: string | null;
}

export interface Connection {
  project_id: string;
  project_name: string;
  system_id: string;
  system_name: string;
  created_at: string;
  config: SystemConfig;
}

export interface ProbeSummary {
  ok: boolean;
  message: string;
  at: string;
}

export interface Capabilities {
  has_chunks: boolean;
  has_scores: boolean;
  has_rewritten_query: boolean;
  has_token_usage: boolean;
}

export interface ProbeResult {
  capabilities: Capabilities;
  observed: Record<string, boolean>;
  error: string | null;
  answer: string | null;
}

export interface Dataset {
  id: string;
  project_id: string;
  name: string;
  source_filename: string;
  headers: string[];
  column_map: Record<string, string>;
  preview: Record<string, string>[];
  case_count: number;
  needs_mapping: boolean;
}

export interface TestCase {
  id: string;
  dataset_id: string;
  source_row: number;
  conversation_id: string | null;
  turn_index: number;
  question: string;
  expected_answer: string | null;
  gold_passage: string | null;
}

export interface JudgeRequest {
  provider: "openai_chat" | "openai_responses";
  model_id: string;
  temperature: 0;
  secondary?: JudgeRequest | null;
}

export interface Estimate {
  target_calls: number;
  counterfactual_calls: number;
  judge_calls: Record<string, number>;
  notes: string[];
}

export interface Run {
  id: string;
  project_id: string;
  dataset_id: string;
  system_config_version_id: string;
  replay_of_run_id: string | null;
  status: string;
  repeats: number;
  max_concurrency: number;
  judge_config: Record<string, unknown>;
  evaluator_ids: string[];
  use_judge_cache: boolean;
  created_at: string;
}

export interface ProgressEvent {
  id: string;
  run_id: string;
  seq: number;
  kind: string;
  message: string;
  payload: Record<string, unknown>;
}

export type LiveState = "queued" | "calling" | "judging" | "done" | "failed" | "not_run" | "stopped";

export interface LiveItem {
  position: number;
  test_case_id: string;
  source_row: number;
  question: string;
  conversation_id: string | null;
  turn_index: number;
  repeat_index: number;
  state: LiveState;
  stage: string | null;
  started_at: string | null;
  stage_started_at: string | null;
  finished_at: string | null;
  attempt: number | null;
  max_attempts: number;
  last_error: string | null;
  error: string | null;
  cause: string | null;
  latency_ms: number | null;
  answer: string | null;
}

export interface RunLive {
  run_id: string;
  status: string;
  message: string;
  total: number;
  done: number;
  failed: number;
  running: number;
  waiting: number;
  remaining: number;
  max_concurrency: number;
  target_timeout_s: number;
  runs_ahead: number;
  busy_run_ids: string[];
  worker: { embedded: boolean; alive: boolean; current_run_id: string | null; heartbeat: string | null };
  items: LiveItem[];
  log: { seq: number; kind: string; message: string; at: string | null; test_case_id: string | null }[];
}

export interface Chunk {
  chunk_key: string;
  rank: number;
  text: string;
  score: number | null;
  source: string | null;
  page: number | null;
  token_length: number | null;
}

export interface Trace {
  id: string;
  run_id: string;
  test_case_id: string;
  conversation_id: string | null;
  turn_index: number;
  kind: string;
  repeat_index: number;
  question: string;
  answer: string | null;
  rewritten_query: string | null;
  error: string | null;
  status: string;
  latency_ms: number | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  model: string | null;
  chunks: Chunk[];
}

export interface MetricResult {
  id: string;
  run_id: string;
  test_case_id: string;
  metric_id: string;
  value: number | null;
  status: string;
  skip_reason: string | null;
  details: Record<string, unknown>;
  rubric_version: number | null;
  judge_model: string | null;
  temperature: number | null;
  judge_role: string | null;
  prompt_hash: string | null;
  repeat_index: number;
  judge_slot: string;
}

export interface MetricSummaryRow {
  value: number | null;
  numerator: number | null;
  denominator: number | null;
  status: string;
  details?: Record<string, unknown>;
}

export interface MetricsResponse {
  rows: MetricResult[];
  summary: {
    metrics: Record<string, MetricSummaryRow>;
    histogram: { start: number; end: number; count: number }[];
    skipped: { reason: string; count: number }[];
    history: Record<string, unknown>;
  };
}

export interface Finding {
  id: string;
  run_id: string;
  rule_id: string;
  cause: string;
  severity: string;
  count: number;
  example_question_ids: string[];
  evidence: Record<string, { true: number; false: number; "n/a": number }>;
  prose?: string;
}

export interface SetupRow {
  id: string;
  setting: string;
  current: string;
  try: string;
  why: string;
}

export interface ReportModel {
  header: Record<string, unknown>;
  score_summary: {
    id: string;
    value: number | null;
    numerator: number | null;
    denominator: number | null;
    status: string;
    skip_reason?: string | null;
  }[];
  skipped: { reason: string; count: number }[];
  failure_causes: Record<string, number>;
  findings: Finding[];
  setup_table: SetupRow[];
  compare: CompareResult | null;
  calibration: CalibrationAgreement;
  summary_text: string;
}

export interface CompareResult {
  run_a: string;
  run_b: string;
  metrics: { metric_id: string; a: number | null; b: number | null; delta: number | null }[];
  resolved: { rule_id: string; count_a: number; count_b: number }[];
  added: { rule_id: string; count_a: number; count_b: number }[];
  still_present: { rule_id: string; count_a: number; count_b: number }[];
}

export interface CalibrationAgreement {
  item_count: number;
  kappa: number | null;
  trusted: boolean;
  warn: boolean;
  message: string;
}

export interface ColumnMap {
  question: string;
  expected_answer?: string | null;
  gold_passage?: string | null;
  conversation_id?: string | null;
}

export interface SystemDraft {
  projectName: string;
  systemName: string;
  url: string;
  requestTemplate: string;
  answerPath: string;
  encoding: "json" | "form";
  testQuery: string;
}
