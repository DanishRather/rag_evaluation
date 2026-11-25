import { useMutation, useQuery } from "@tanstack/react-query";

import { useUiStore } from "../../model/stores/ui";
import type { MetricResult, Trace } from "../../model/types";
import { queryKeys } from "../../services";
import { useServices } from "../services";

export function useResults(runId: string) {
  const services = useServices();
  const tab = useUiStore((state) => state.resultsTab);
  const setResultsTab = useUiStore((state) => state.setResultsTab);
  const datasetId = useUiStore((state) => state.datasetId);
  const traces = useQuery({ queryKey: queryKeys.traces(runId), queryFn: () => services.results.traces(runId) });
  const metrics = useQuery({ queryKey: queryKeys.metrics(runId), queryFn: () => services.results.metrics(runId) });
  const cases = useQuery({
    queryKey: queryKeys.cases(datasetId ?? "none"),
    queryFn: () => services.dataset.cases(datasetId as string),
    enabled: Boolean(datasetId),
  });
  const label = useMutation({
    mutationFn: (body: { testCaseId: string; humanCorrect: boolean }) =>
      services.calibration.save(datasetId as string, [{ test_case_id: body.testCaseId, human_correct: body.humanCorrect }]),
  });
  return {
    tab,
    setResultsTab,
    traces: traces.data ?? [],
    cases: cases.data ?? [],
    metrics: metrics.data ?? null,
    loading: traces.isLoading || metrics.isLoading,
    error: errorOf(traces.error) || errorOf(metrics.error),
    retry: () => {
      void traces.refetch();
      void metrics.refetch();
    },
    label: (testCaseId: string, humanCorrect: boolean) => label.mutate({ testCaseId, humanCorrect }),
  };
}

export function useChunkingTrace(traces: Trace[], rows: MetricResult[]) {
  const primary = traces.filter((trace) => trace.kind === "primary" && trace.status === "ok");
  const selected = primary[0] ?? null;
  const metric = rows.find((row) => row.metric_id === "chunk_split" && row.test_case_id === selected?.test_case_id);
  return { selected, metric, emptyReason: emptyChunkReason(selected, metric) };
}

export function useHistoryTrace(traces: Trace[], rows: MetricResult[]) {
  const followups = traces.filter((trace) => trace.kind === "primary" && trace.turn_index > 0);
  const selected = followups[0] ?? null;
  const counter = traces.find(
    (trace) => trace.kind === "standalone_counterfactual" && trace.test_case_id === selected?.test_case_id,
  );
  const metric = rows.find((row) => row.metric_id === "history_failure" && row.test_case_id === selected?.test_case_id);
  return { selected, counter, metric, emptyReason: emptyHistoryReason(traces, selected, metric) };
}

function emptyChunkReason(trace: Trace | null, metric: MetricResult | undefined) {
  if (!trace) {
    return "This run has no successful trace yet.";
  }
  if (!trace.chunks.length) {
    return "The trace has no chunks.";
  }
  if (metric?.skip_reason === "no gold passage") {
    return "The case was skipped for no gold passage.";
  }
  return "";
}

function emptyHistoryReason(traces: Trace[], selected: Trace | null, metric: MetricResult | undefined) {
  if (!traces.length) {
    return "The run has no conversations.";
  }
  if (!selected) {
    return "The case is not a follow-up.";
  }
  if (metric?.skip_reason === "no standalone trace") {
    return "no standalone trace";
  }
  return "";
}

function errorOf(error: unknown) {
  return error instanceof Error ? error.message : "";
}
