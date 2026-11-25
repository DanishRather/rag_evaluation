import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { useUiStore } from "../../model/stores/ui";
import type { JudgeRequest } from "../../model/types";
import { queryKeys, sendsEachQuestion } from "../../services";
import { useServices } from "../services";

const TERMINAL = new Set(["succeeded", "failed", "cancelled"]);

export function isTerminal(status: string | undefined) {
  return status !== undefined && TERMINAL.has(status);
}

export function useRunControl() {
  const services = useServices();
  const projectId = useUiStore((state) => state.projectId);
  const datasetId = useUiStore((state) => state.datasetId);
  const configId = useUiStore((state) => state.configId);
  const lastRunId = useUiStore((state) => state.lastRunId);
  const setLastRunId = useUiStore((state) => state.setLastRunId);
  const [maxConcurrency, setMaxConcurrency] = useState(1);
  const [targetTimeout, setTargetTimeout] = useState(180);
  const [targetAttempts, setTargetAttempts] = useState(2);
  const [checks, setChecks] = useState({
    quality: true,
    retrieval: true,
    chunking: true,
    history: true,
    model: true,
  });
  const [modelId, setModelId] = useState("");
  const [provider, setProvider] = useState<JudgeRequest["provider"]>("openai_chat");
  const defaults = useQuery({
    queryKey: ["judge-defaults"],
    queryFn: () => services.run.defaults(),
  });
  const appliedDefaults = useRef(false);
  useEffect(() => {
    if (appliedDefaults.current || !defaults.data?.model_id) {
      return;
    }
    appliedDefaults.current = true;
    setProvider(defaults.data.provider);
    setModelId((current) => current.trim() || defaults.data.model_id);
  }, [defaults.data]);
  const [repeats, setRepeats] = useState(1);
  const [secondaryModel, setSecondaryModel] = useState("");
  const [runId, setRunId] = useState<string | null>(lastRunId);
  const judge: JudgeRequest = {
    provider,
    model_id: modelId.trim(),
    temperature: 0,
    secondary: secondaryModel.trim()
      ? { provider, model_id: secondaryModel.trim(), temperature: 0 }
      : null,
  };
  const estimate = useMutation({
    mutationFn: () =>
      services.run.estimate({
        datasetId: datasetId as string,
        configId: configId as string,
        judge,
        repeats,
      }),
  });
  const start = useMutation({
    mutationFn: () =>
      services.run.start({
        project_id: projectId as string,
        dataset_id: datasetId as string,
        system_config_version_id: configId as string,
        judge,
        repeats,
        max_concurrency: Math.max(1, maxConcurrency),
        price_table: null,
        use_judge_cache: false,
        target_timeout_s: Math.max(5, targetTimeout),
        target_max_attempts: Math.max(1, targetAttempts),
        evaluator_ids: selectedEvaluators(checks),
      }),
    onSuccess: (run) => {
      setRunId(run.id);
      setLastRunId(run.id);
    },
  });
  const cancel = useMutation({
    mutationFn: () => services.run.cancel(runId as string),
  });
  const resume = useMutation({
    mutationFn: () => services.run.resume(runId as string),
  });
  const reevaluate = useMutation({
    mutationFn: () => services.run.reevaluate(runId as string, judge),
    onSuccess: (run) => {
      setRunId(run.id);
      setLastRunId(run.id);
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) => services.run.delete(id),
    onSuccess: (_result, id) => {
      if (id === runId) {
        setRunId(null);
        setLastRunId(null);
      }
    },
  });
  const clearFailed = useMutation({
    mutationFn: () => services.run.deleteFailed(),
    onSuccess: () => {
      setRunId(null);
      setLastRunId(null);
    },
  });
  return {
    modelId,
    setModelId,
    provider,
    setProvider,
    repeats,
    setRepeats,
    maxConcurrency,
    setMaxConcurrency,
    targetTimeout,
    setTargetTimeout,
    targetAttempts,
    setTargetAttempts,
    checks,
    setChecks,
    secondaryModel,
    setSecondaryModel,
    canStart: Boolean(datasetId && configId && projectId && modelId.trim() && someCheck(checks)),
    estimate: estimate.data ?? null,
    requestEstimate: () => estimate.mutate(),
    startRun: () => start.mutate(),
    cancelRun: () => cancel.mutate(),
    resumeRun: () => resume.mutate(),
    reevaluateRun: () => reevaluate.mutate(),
    deleteRun: (id: string) => remove.mutate(id),
    clearFailedRuns: () => clearFailed.mutate(),
    clearing: clearFailed.isPending,
    watchRun: (id: string) => {
      setRunId(id);
      setLastRunId(id);
    },
    runId,
    error:
      errorOf(start.error) ||
      errorOf(estimate.error) ||
      errorOf(cancel.error) ||
      errorOf(resume.error) ||
      errorOf(reevaluate.error) ||
      errorOf(remove.error) ||
      errorOf(clearFailed.error),
    starting: start.isPending,
  };
}

export function useRunLive(runId: string | null) {
  const services = useServices();
  const live = useQuery({
    queryKey: queryKeys.live(runId ?? "none"),
    queryFn: () => services.run.live(runId as string),
    enabled: Boolean(runId),
    refetchInterval: (query) => (isTerminal(query.state.data?.status) ? false : 1000),
  });
  const status = live.data?.status;
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!status || isTerminal(status)) {
      return;
    }
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [status]);
  return { live: live.data ?? null, now, error: errorOf(live.error) };
}

export function useRunTarget() {
  const services = useServices();
  const configId = useUiStore((state) => state.configId);
  const datasetId = useUiStore((state) => state.datasetId);
  const systemName = useUiStore((state) => state.systemName);
  const endpointUrl = useUiStore((state) => state.endpointUrl);
  const probes = useUiStore((state) => state.probes);
  const connections = useQuery({
    queryKey: queryKeys.connections,
    queryFn: () => services.system.connections(),
  });
  const dataset = useQuery({
    queryKey: queryKeys.dataset(datasetId ?? "none"),
    queryFn: () => services.dataset.get(datasetId as string),
    enabled: Boolean(datasetId),
  });
  const connection = connections.data?.find((item) => item.config.id === configId) ?? null;
  const template = String(connection?.config.adapter_settings.request_template ?? "");
  return {
    connected: Boolean(configId),
    sendsQuestions: !connection || !template || sendsEachQuestion(template),
    systemName: connection?.system_name ?? systemName,
    url: String(connection?.config.adapter_settings.url ?? endpointUrl),
    encoding: connection?.config.adapter_settings.encoding === "form" ? "form" : "json",
    probe: configId ? (probes[configId] ?? null) : null,
    dataset: dataset.data ?? null,
  };
}

export function useRecentRuns() {
  const services = useServices();
  const projectId = useUiStore((state) => state.projectId);
  const runs = useQuery({
    queryKey: queryKeys.runs(projectId ?? "all"),
    queryFn: () => services.run.list(projectId),
    refetchInterval: 3000,
  });
  return { runs: runs.data ?? [] };
}

function errorOf(error: unknown) {
  return error instanceof Error ? error.message : "";
}

const EVALUATORS = {
  quality: ["correctness", "faithfulness"],
  retrieval: ["hit", "mrr", "precision_at_k", "recall_at_k"],
  chunking: ["chunk_split"],
  history: ["history_failure"],
  model: ["runtime", "variance"],
} as const;

function selectedEvaluators(checks: Record<keyof typeof EVALUATORS, boolean>): string[] | null {
  const keys = Object.keys(EVALUATORS) as (keyof typeof EVALUATORS)[];
  if (keys.every((key) => checks[key])) {
    return null;
  }
  return keys.flatMap((key) => (checks[key] ? [...EVALUATORS[key]] : []));
}

function someCheck(checks: Record<keyof typeof EVALUATORS, boolean>) {
  return Object.values(checks).some(Boolean);
}
