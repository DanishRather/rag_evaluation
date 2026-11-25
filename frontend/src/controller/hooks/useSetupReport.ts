import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { queryKeys } from "../../services";
import { useServices } from "../services";

export function useSetupReport(runId: string) {
  const services = useServices();
  const report = useQuery({ queryKey: queryKeys.report(runId), queryFn: () => services.report.get(runId) });
  const run = useQuery({ queryKey: queryKeys.run(runId), queryFn: () => services.run.get(runId) });
  return {
    report: report.data ?? null,
    run: run.data ?? null,
    loading: report.isLoading || run.isLoading,
    error: errorOf(report.error),
    retry: () => report.refetch(),
    htmlPath: services.report.htmlPath(runId),
    pdfPath: services.report.pdfPath(runId),
  };
}

export function useCompareRuns(runId: string) {
  const services = useServices();
  const [otherId, setOtherId] = useState("");
  const compare = useQuery({
    queryKey: queryKeys.compare(runId, otherId),
    queryFn: () => services.report.compare(runId, otherId),
    enabled: Boolean(otherId.trim()),
  });
  return {
    otherId,
    setOtherId,
    compare: compare.data ?? null,
    error: errorOf(compare.error),
  };
}

function errorOf(error: unknown) {
  return error instanceof Error ? error.message : "";
}
