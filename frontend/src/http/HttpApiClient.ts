import type { ApiClient, EstimateBody, RunBody } from "../model/api/client";
import type { ColumnMap, JudgeRequest, ProgressEvent } from "../model/types";

export class HttpApiClient implements ApiClient {
  constructor(private readonly base = "") {}

  listProjects() {
    return this.send("GET", "/api/projects");
  }

  createProject(name: string) {
    return this.send("POST", "/api/projects", { name });
  }

  getProject(id: string) {
    return this.send("GET", `/api/projects/${id}`);
  }

  createSystem(projectId: string, name: string) {
    return this.send("POST", `/api/projects/${projectId}/systems`, { name });
  }

  listSystems(projectId: string) {
    return this.send("GET", `/api/projects/${projectId}/systems`);
  }

  listConnections() {
    return this.send("GET", "/api/connections");
  }

  createConfig(
    systemId: string,
    body: {
      adapter_type: string;
      adapter_settings: Record<string, unknown>;
      profile_settings: Record<string, unknown>;
      auth_secret: string | null;
    },
  ) {
    return this.send("POST", `/api/systems/${systemId}/configs`, body);
  }

  listConfigs(systemId: string) {
    return this.send("GET", `/api/systems/${systemId}/configs`);
  }

  probe(configId: string, question: string) {
    return this.send("POST", `/api/system-configs/${configId}/probe`, { question });
  }

  deleteSystem(systemId: string) {
    return this.send("DELETE", `/api/systems/${systemId}`);
  }

  deleteBrokenConnections() {
    return this.send("DELETE", "/api/connections/broken");
  }

  uploadDataset(projectId: string, file: File) {
    const body = new FormData();
    body.append("file", file);
    return this.send("POST", `/api/projects/${projectId}/datasets`, body);
  }

  listDatasets(projectId: string) {
    return this.send("GET", `/api/projects/${projectId}/datasets`);
  }

  deleteDataset(datasetId: string) {
    return this.send("DELETE", `/api/datasets/${datasetId}`);
  }

  saveMapping(datasetId: string, mapping: ColumnMap) {
    return this.send("PUT", `/api/datasets/${datasetId}/mapping`, mapping);
  }

  getDataset(datasetId: string) {
    return this.send("GET", `/api/datasets/${datasetId}`);
  }

  listCases(datasetId: string) {
    return this.send("GET", `/api/datasets/${datasetId}/cases`);
  }

  judgeDefaults() {
    return this.send("GET", "/api/runs/judge-defaults");
  }

  estimate(body: EstimateBody) {
    return this.send("POST", "/api/runs/estimate", body);
  }

  createRun(body: RunBody, idempotencyKey?: string) {
    return this.send("POST", "/api/runs", body, idempotencyKey);
  }

  getRun(runId: string) {
    return this.send("GET", `/api/runs/${runId}`);
  }

  listRuns(projectId?: string | null) {
    const query = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
    return this.send("GET", `/api/runs${query}`);
  }

  getRunLive(runId: string) {
    return this.send("GET", `/api/runs/${runId}/live`);
  }

  cancelRun(runId: string) {
    return this.send("POST", `/api/runs/${runId}/cancel`);
  }

  resumeRun(runId: string) {
    return this.send("POST", `/api/runs/${runId}/resume`);
  }

  deleteRun(runId: string) {
    return this.send("DELETE", `/api/runs/${runId}`);
  }

  deleteFailedRuns() {
    return this.send("DELETE", "/api/runs/failed");
  }

  reevaluate(runId: string, body: { judge?: JudgeRequest | null; repeats?: number | null; use_judge_cache?: boolean | null }) {
    return this.send("POST", `/api/runs/${runId}/reevaluate`, body);
  }

  subscribe(runId: string, onEvent: (event: ProgressEvent) => void) {
    const source = new EventSource(`${this.base}/api/runs/${runId}/events`);
    source.onmessage = (message) => {
      onEvent(JSON.parse(message.data) as ProgressEvent);
    };
    return () => source.close();
  }

  listTraces(runId: string) {
    return this.send("GET", `/api/runs/${runId}/traces`);
  }

  listMetrics(runId: string) {
    return this.send("GET", `/api/runs/${runId}/metrics`);
  }

  listFindings(runId: string) {
    return this.send("GET", `/api/runs/${runId}/findings`);
  }

  getReport(runId: string) {
    return this.send("GET", `/api/runs/${runId}/report`);
  }

  reportPath(runId: string, kind: "html" | "pdf") {
    const suffix = kind === "html" ? "html" : "pdf";
    return `${this.base}/api/runs/${runId}/report.${suffix}`;
  }

  compare(runA: string, runB: string) {
    return this.send("GET", `/api/runs/compare?run_a=${encodeURIComponent(runA)}&run_b=${encodeURIComponent(runB)}`);
  }

  saveLabels(datasetId: string, labels: { test_case_id: string; human_correct: boolean }[]) {
    return this.send("PUT", `/api/datasets/${datasetId}/calibration-labels`, { labels });
  }

  calibration(runId: string) {
    return this.send("GET", `/api/runs/${runId}/calibration`);
  }

  private async send(method: string, path: string, body?: unknown, idempotencyKey?: string) {
    const headers: Record<string, string> = {};
    let payload: BodyInit | undefined;
    if (body instanceof FormData) {
      payload = body;
    } else if (body !== undefined) {
      headers["content-type"] = "application/json";
      payload = JSON.stringify(body);
    }
    if (idempotencyKey) {
      headers["Idempotency-Key"] = idempotencyKey;
    }
    const response = await fetch(`${this.base}${path}`, { method, headers, body: payload });
    if (!response.ok) {
      throw new Error(await errorMessage(response));
    }
    if (response.status === 204) {
      return undefined;
    }
    return response.json();
  }
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (body?.error?.message) {
      return String(body.error.message);
    }
    if (response.status === 404) {
      return "The evaluation API is not running. Start it with uv run main.py. It listens on port 27463.";
    }
  } catch {
    return response.statusText || "Request failed";
  }
  return response.statusText || "Request failed";
}
