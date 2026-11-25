import type { QueryClient } from "@tanstack/react-query";

import type { ApiClient, RunBody } from "../model/api/client";
import type { ColumnMap, Connection, Dataset, JudgeRequest, ProbeResult, ProbeSummary, ProgressEvent, SystemDraft } from "../model/types";

export const queryKeys = {
  projects: ["projects"] as const,
  connections: ["connections"] as const,
  systemConfig: (id: string) => ["system-config", id] as const,
  datasets: (projectId: string) => ["datasets", projectId] as const,
  dataset: (id: string) => ["dataset", id] as const,
  cases: (id: string) => ["dataset", id, "cases"] as const,
  runs: (projectId: string) => ["runs", projectId] as const,
  run: (id: string) => ["run", id] as const,
  live: (id: string) => ["run", id, "live"] as const,
  progress: (id: string) => ["run", id, "progress"] as const,
  metrics: (id: string) => ["run", id, "metrics"] as const,
  traces: (id: string) => ["run", id, "traces"] as const,
  findings: (id: string) => ["run", id, "findings"] as const,
  report: (id: string) => ["run", id, "report"] as const,
  compare: (a: string, b: string) => ["compare", a, b] as const,
};

function adapterSettings(draft: SystemDraft): Record<string, unknown> {
  const form = draft.encoding === "form";
  const answerPath = draft.answerPath.trim() || (form ? "$.content" : "$.answer");
  const responseMap: Record<string, string> = { answer: answerPath };
  if (form) {
    responseMap.chunks = "$.contexts[*]";
    responseMap.chunk_text = "$.text";
    responseMap.chunk_id = "$.id";
    responseMap.chunk_source = "$.source";
    responseMap.prompt_tokens = "$.metrics.input_tokens";
    responseMap.completion_tokens = "$.metrics.output_tokens";
    responseMap.model = "$.model";
  }
  return {
    url: draft.url.trim(),
    request_template: draft.requestTemplate,
    response_map: responseMap,
    encoding: form ? "form" : "json",
  };
}

export function draftFromConnection(connection: Connection): SystemDraft {
  const settings = connection.config.adapter_settings;
  const responseMap = (settings.response_map ?? {}) as Record<string, unknown>;
  return {
    projectName: connection.project_name,
    systemName: connection.system_name,
    url: String(settings.url ?? ""),
    requestTemplate: String(settings.request_template ?? ""),
    answerPath: String(responseMap.answer ?? "$.answer"),
    encoding: settings.encoding === "form" ? "form" : "json",
    testQuery: String((connection.config.profile_settings.test_query as string | undefined) ?? ""),
  };
}

export function sendsEachQuestion(template: string): boolean {
  return /\{\{[^}]*\bquestion\b[^}]*\}\}/.test(template);
}

export function summarizeProbe(probe: ProbeResult): ProbeSummary {
  const at = new Date().toISOString();
  if (probe.error) {
    return { ok: false, message: probe.error, at };
  }
  if (!probe.answer) {
    return { ok: false, message: "The endpoint answered, but the answer text path found nothing.", at };
  }
  const answer = probe.answer.length > 160 ? `${probe.answer.slice(0, 159)}…` : probe.answer;
  return { ok: true, message: answer, at };
}

export function createServices(client: ApiClient, queryClient: QueryClient) {
  return {
    system: {
      listProjects: () => client.listProjects(),
      connections: () => client.listConnections(),
      connect: async (draft: SystemDraft, currentProjectId: string | null = null) => {
        const projectName = draft.projectName.trim();
        const systemName = draft.systemName.trim();
        const projects = await client.listProjects();
        const project =
          projects.find((item) => item.id === currentProjectId && item.name === projectName) ??
          [...projects].reverse().find((item) => item.name === projectName) ??
          (await client.createProject(projectName));
        const systems = await client.listSystems(project.id);
        const system =
          [...systems].reverse().find((item) => item.name === systemName) ?? (await client.createSystem(project.id, systemName));
        const config = await client.createConfig(system.id, {
          adapter_type: "http",
          adapter_settings: adapterSettings(draft),
          profile_settings: { test_query: draft.testQuery.trim() },
          auth_secret: null,
        });
        queryClient.setQueryData(queryKeys.systemConfig(config.id), config);
        await queryClient.invalidateQueries({ queryKey: queryKeys.connections });
        const probe = await client.probe(config.id, draft.testQuery.trim());
        return { project, system, config, probe };
      },
      probe: (configId: string, question: string) => client.probe(configId, question),
      delete: async (systemId: string) => {
        await client.deleteSystem(systemId);
        void queryClient.invalidateQueries({ queryKey: queryKeys.connections });
      },
      deleteBroken: async () => {
        const result = await client.deleteBrokenConnections();
        void queryClient.invalidateQueries({ queryKey: queryKeys.connections });
        void queryClient.invalidateQueries({ queryKey: ["runs"] });
        return result;
      },
    },
    dataset: {
      upload: async (projectId: string, file: File) => {
        const dataset = await client.uploadDataset(projectId, file);
        void queryClient.invalidateQueries({ queryKey: queryKeys.datasets(projectId) });
        return dataset;
      },
      list: (projectId: string) => client.listDatasets(projectId),
      delete: async (datasetId: string, projectId: string) => {
        await client.deleteDataset(datasetId);
        queryClient.setQueryData<Dataset[]>(queryKeys.datasets(projectId), (current) =>
          (current ?? []).filter((item) => item.id !== datasetId),
        );
        void queryClient.invalidateQueries({ queryKey: queryKeys.datasets(projectId) });
        void queryClient.invalidateQueries({ queryKey: ["runs"] });
      },
      saveMapping: async (datasetId: string, mapping: ColumnMap) => {
        const dataset = await client.saveMapping(datasetId, mapping);
        queryClient.setQueryData(queryKeys.dataset(datasetId), dataset);
        return dataset;
      },
      get: (datasetId: string) => client.getDataset(datasetId),
      cases: (datasetId: string) => client.listCases(datasetId),
    },
    run: {
      defaults: () => client.judgeDefaults(),
      estimate: (body: { datasetId: string; configId: string; judge: JudgeRequest; repeats: number }) =>
        client.estimate({
          dataset_id: body.datasetId,
          system_config_version_id: body.configId,
          judge: body.judge,
          repeats: body.repeats,
        }),
      start: async (body: RunBody) => {
        const run = await client.createRun(body);
        queryClient.setQueryData(queryKeys.run(run.id), run);
        void queryClient.invalidateQueries({ queryKey: ["runs"] });
        return run;
      },
      get: (runId: string) => client.getRun(runId),
      list: (projectId: string | null) => client.listRuns(projectId),
      live: (runId: string) => client.getRunLive(runId),
      cancel: async (runId: string) => {
        const run = await client.cancelRun(runId);
        void queryClient.invalidateQueries({ queryKey: queryKeys.live(runId) });
        void queryClient.invalidateQueries({ queryKey: ["runs"] });
        return run;
      },
      resume: async (runId: string) => {
        const run = await client.resumeRun(runId);
        void queryClient.invalidateQueries({ queryKey: queryKeys.live(runId) });
        void queryClient.invalidateQueries({ queryKey: ["runs"] });
        return run;
      },
      reevaluate: async (runId: string, judge: JudgeRequest) => {
        const run = await client.reevaluate(runId, { judge });
        void queryClient.invalidateQueries({ queryKey: ["runs"] });
        return run;
      },
      delete: async (runId: string) => {
        await client.deleteRun(runId);
        queryClient.removeQueries({ queryKey: queryKeys.live(runId) });
        void queryClient.invalidateQueries({ queryKey: ["runs"] });
      },
      deleteFailed: async () => {
        const result = await client.deleteFailedRuns();
        void queryClient.invalidateQueries({ queryKey: ["runs"] });
        return result;
      },
      watch: (runId: string) =>
        client.subscribe(runId, (event: ProgressEvent) => {
          queryClient.setQueryData<ProgressEvent[]>(queryKeys.progress(runId), (current = []) => {
            if (current.some((item) => item.id === event.id)) {
              return current;
            }
            return [...current, event];
          });
          if (event.kind === "run_finished" || event.kind === "run_failed" || event.kind === "run_cancelled") {
            void queryClient.invalidateQueries({ queryKey: queryKeys.run(runId) });
          }
        }),
    },
    results: {
      traces: (runId: string) => client.listTraces(runId),
      metrics: (runId: string) => client.listMetrics(runId),
    },
    report: {
      get: (runId: string) => client.getReport(runId),
      findings: (runId: string) => client.listFindings(runId),
      compare: (runA: string, runB: string) => client.compare(runA, runB),
      htmlPath: (runId: string) => client.reportPath(runId, "html"),
      pdfPath: (runId: string) => client.reportPath(runId, "pdf"),
    },
    calibration: {
      save: (datasetId: string, labels: { test_case_id: string; human_correct: boolean }[]) =>
        client.saveLabels(datasetId, labels),
      agreement: (runId: string) => client.calibration(runId),
    },
  };
}

export type Services = ReturnType<typeof createServices>;
