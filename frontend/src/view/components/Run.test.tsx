import { render, screen, within } from "@testing-library/react";

import type { LiveItem, RunLive } from "../../model/types";
import { LiveRunPanel } from "./Run";

function item(position: number, state: LiveItem["state"], extra: Partial<LiveItem> = {}): LiveItem {
  return {
    position,
    test_case_id: `case-${position}`,
    source_row: position,
    question: `Question ${position}`,
    conversation_id: null,
    turn_index: 0,
    repeat_index: 0,
    state,
    stage: null,
    started_at: null,
    stage_started_at: null,
    finished_at: null,
    attempt: null,
    max_attempts: 2,
    last_error: null,
    error: null,
    cause: null,
    latency_ms: null,
    answer: null,
    ...extra,
  };
}

function live(extra: Partial<RunLive> = {}): RunLive {
  return {
    run_id: "run-12345678",
    status: "running",
    message: "",
    total: 4,
    done: 1,
    failed: 0,
    running: 1,
    waiting: 2,
    remaining: 3,
    max_concurrency: 1,
    target_timeout_s: 180,
    runs_ahead: 0,
    busy_run_ids: [],
    worker: { embedded: true, alive: true, current_run_id: "run-12345678", heartbeat: null },
    items: [
      item(1, "done", { finished_at: "2026-11-25T10:00:05Z", latency_ms: 4200, answer: "Answer 1" }),
      item(2, "calling", { stage: "target", stage_started_at: "2026-11-25T10:00:06Z", attempt: 1 }),
      item(3, "queued"),
      item(4, "queued"),
    ],
    log: [],
    ...extra,
  };
}

test("shows counts, the running question, and the queue", () => {
  render(<LiveRunPanel live={live()} now={Date.parse("2026-11-25T10:00:18Z")} error="" />);
  expect(screen.getByText("1 of 4 questions computed (25%)")).toBeInTheDocument();
  const remaining = screen.getByText("Still to compute").parentElement as HTMLElement;
  expect(within(remaining).getByText("3")).toBeInTheDocument();
  const running = screen.getByRole("heading", { name: "Now running" }).nextElementSibling as HTMLElement;
  expect(within(running).getByText("Question 2")).toBeInTheDocument();
  expect(within(running).getByText("Waiting for the endpoint answer")).toBeInTheDocument();
  expect(within(running).getByText("12s")).toBeInTheDocument();
  const next = screen.getByRole("heading", { name: "Up next" }).nextElementSibling as HTMLElement;
  expect(within(next).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["Question 3", "Question 4"]);
});

test("explains why a queued run is waiting", () => {
  render(
    <LiveRunPanel
      live={live({ status: "queued", done: 0, running: 0, waiting: 4, remaining: 4, runs_ahead: 2, items: [item(1, "queued")] })}
      now={0}
      error=""
    />,
  );
  expect(screen.getByText(/Waiting behind 2 other runs/)).toBeInTheDocument();
});
