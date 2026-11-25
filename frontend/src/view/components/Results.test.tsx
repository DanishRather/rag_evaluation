import { render, screen } from "@testing-library/react";

import type { Estimate } from "../../model/types";
import { EmptyState, ErrorState } from "./Chrome";
import { EstimateBanner } from "./Run";
import { QuestionTable, passagesFromAnswer } from "./Results";

const estimate: Estimate = {
  target_calls: 100,
  counterfactual_calls: 20,
  judge_calls: { correctness: 80, usefulness_worst_case: 350 },
  notes: ["Usefulness calls only the gray band, not every chunk."],
};

test("estimate banner lists judge calls and extra target calls", () => {
  render(<EstimateBanner estimate={estimate} />);
  expect(screen.getByText(/Target calls 100/)).toBeInTheDocument();
  expect(screen.getByText("Correctness")).toBeInTheDocument();
  expect(screen.getByText("350")).toBeInTheDocument();
  expect(screen.getByText(/gray band/)).toBeInTheDocument();
});

test("empty and error states render their copy", () => {
  render(
    <div>
      <EmptyState title="No traces yet" body="The run has no traces yet." />
      <ErrorState message="Start failed" />
    </div>,
  );
  expect(screen.getByRole("status")).toHaveTextContent("No traces yet");
  expect(screen.getByRole("alert")).toHaveTextContent("Start failed");
});

test("question table shows stored scores without recomputing them", () => {
  render(
    <QuestionTable
      rows={[
        {
          testCaseId: "case-1",
          question: "What is the refund window?",
          answer: "30 days",
          status: "ok",
          correctness: metric("correctness", 1, 1, 1),
          faithfulness: metric("faithfulness", 0.5, 1, 2),
        },
      ]}
    />,
  );
  expect(screen.getByText("What is the refund window?")).toBeInTheDocument();
  expect(screen.getByText("Correct")).toBeInTheDocument();
  expect(screen.getByText("Not grounded")).toBeInTheDocument();
  expect(screen.getByText("100% (1/1)")).toBeInTheDocument();
  expect(screen.getByText("50% (1/2)")).toBeInTheDocument();
});

test("a reference section in the stored answer is shown as a cited passage", () => {
  const passages = passagesFromAnswer(
    "The clause requires assistance.\n\n## References\n\n- [constitution.pdf](https://example.test/constitution.pdf) — Constitution of India, pp. 211–212 [C217]\n",
    [],
  );
  expect(passages).toHaveLength(1);
  expect(passages[0]?.source).toBe("constitution.pdf");
  expect(passages[0]?.chunk_key).toBe("C217");
});

function metric(id: string, value: number, numerator: number, denominator: number) {
  return {
    id,
    run_id: "run",
    test_case_id: "case-1",
    metric_id: id,
    value,
    status: "ok",
    skip_reason: null,
    details: { numerator, denominator },
    rubric_version: 1,
    judge_model: "judge",
    temperature: 0,
    judge_role: id,
    prompt_hash: "hash",
    repeat_index: 0,
    judge_slot: "primary",
  };
}
