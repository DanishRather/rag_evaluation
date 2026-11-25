import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, act } from "@testing-library/react";
import type { ReactNode } from "react";

import { useUiStore } from "../../model/stores/ui";
import { createServices } from "../../services";
import { ServicesProvider } from "../services";
import { useRunControl } from "./useRunControl";

test("the run hook asks the feature service to estimate and start", async () => {
  const estimate = vi.fn().mockResolvedValue({
    target_calls: 1,
    counterfactual_calls: 0,
    judge_calls: { report_writer: 1 },
    notes: [],
  });
  const createRun = vi.fn().mockResolvedValue({
    id: "run-1",
    project_id: "p",
    dataset_id: "d",
    system_config_version_id: "c",
    replay_of_run_id: null,
    status: "queued",
    repeats: 1,
    max_concurrency: 4,
    judge_config: {},
    evaluator_ids: [],
    use_judge_cache: false,
    created_at: "now",
  });
  const client = {
    estimate,
    createRun,
    judgeDefaults: vi.fn().mockResolvedValue({ provider: "openai_chat", model_id: "" }),
  } as never;
  useUiStore.setState({ projectId: "p", datasetId: "d", configId: "c" });
  const queryClient = new QueryClient();
  const services = createServices(client, queryClient);
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <ServicesProvider services={services}>{children}</ServicesProvider>
    </QueryClientProvider>
  );
  const hook = renderHook(() => useRunControl(), { wrapper });
  act(() => hook.result.current.setModelId("judge-model"));
  await act(async () => {
    hook.result.current.requestEstimate();
    hook.result.current.startRun();
  });
  expect(estimate).toHaveBeenCalledWith({
    dataset_id: "d",
    system_config_version_id: "c",
    judge: { provider: "openai_chat", model_id: "judge-model", temperature: 0, secondary: null },
    repeats: 1,
  });
  expect(createRun).toHaveBeenCalled();
});
