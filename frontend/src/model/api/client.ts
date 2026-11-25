import type {
  CalibrationAgreement,
  ColumnMap,
  CompareResult,
  Connection,
  Dataset,
  Estimate,
  Finding,
  JudgeRequest,
  MetricsResponse,
  ProbeResult,
  ProgressEvent,
  Project,
  ReportModel,
  Run,
  RunLive,
  SystemConfig,
  SystemRecord,
  TestCase,
  Trace,
} from "../types";

export interface EstimateBody {
  dataset_id: string;
  system_config_version_id: string;
  judge: JudgeRequest;
  repeats: number;
}

export interface RunBody extends EstimateBody {
  project_id: string;
  max_concurrency: number;
  price_table: Record<string, { input_per_million: number; output_per_million: number }> | null;
  use_judge_cache: boolean;
  target_timeout_s: number;
  target_max_attempts: number;
  evaluator_ids: string[] | null;
}

export interface ApiClient {
  listProjects(): Promise<Project[]>;
  createProject(name: string): Promise<Project>;
  getProject(id: string): Promise<Project>;
  createSystem(projectId: string, name: string): Promise<SystemRecord>;
  listSystems(projectId: string): Promise<SystemRecord[]>;
  listConnections(): Promise<Connection[]>;
  createConfig(
    systemId: string,
    body: {
      adapter_type: string;
      adapter_settings: Record<string, unknown>;
      profile_settings: Record<string, unknown>;
      auth_secret: string | null;
    },
  ): Promise<SystemConfig>;
  listConfigs(systemId: string): Promise<SystemConfig[]>;
  probe(configId: string, question: string): Promise<ProbeResult>;
  deleteSystem(systemId: string): Promise<void>;
  deleteBrokenConnections(): Promise<{ deleted: number }>;
  uploadDataset(projectId: string, file: File): Promise<Dataset>;
  listDatasets(projectId: string): Promise<Dataset[]>;
  deleteDataset(datasetId: string): Promise<void>;
  saveMapping(datasetId: string, mapping: ColumnMap): Promise<Dataset>;
  getDataset(datasetId: string): Promise<Dataset>;
  listCases(datasetId: string): Promise<TestCase[]>;
  judgeDefaults(): Promise<Pick<JudgeRequest, "provider" | "model_id">>;
  estimate(body: EstimateBody): Promise<Estimate>;
  createRun(body: RunBody, idempotencyKey?: string): Promise<Run>;
  getRun(runId: string): Promise<Run>;
  listRuns(projectId?: string | null): Promise<Run[]>;
  getRunLive(runId: string): Promise<RunLive>;
  cancelRun(runId: string): Promise<Run>;
  resumeRun(runId: string): Promise<Run>;
  deleteRun(runId: string): Promise<void>;
  deleteFailedRuns(): Promise<{ deleted: number }>;
  reevaluate(runId: string, body: { judge?: JudgeRequest | null; repeats?: number | null; use_judge_cache?: boolean | null }): Promise<Run>;
  subscribe(runId: string, onEvent: (event: ProgressEvent) => void): () => void;
  listTraces(runId: string): Promise<Trace[]>;
  listMetrics(runId: string): Promise<MetricsResponse>;
  listFindings(runId: string): Promise<Finding[]>;
  getReport(runId: string): Promise<ReportModel>;
  reportPath(runId: string, kind: "html" | "pdf"): string;
  compare(runA: string, runB: string): Promise<CompareResult>;
  saveLabels(datasetId: string, labels: { test_case_id: string; human_correct: boolean }[]): Promise<unknown>;
  calibration(runId: string): Promise<CalibrationAgreement>;
}
