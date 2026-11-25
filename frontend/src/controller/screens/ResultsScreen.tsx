import type { KeyboardEvent } from "react";
import { useParams } from "react-router-dom";

import type { ResultsTab } from "../../model/types";
import { EmptyState, ErrorState, LoadingSkeleton, PageHead } from "../../view/components/Chrome";
import { formatDuration } from "../../view/format";
import { ModelCostTable, QuestionTable, RetrievalTable, RunFacts, ScoreCards, citedPassages } from "../../view/components/Results";
import { useResults } from "../hooks/useResults";

const TABS: { id: ResultsTab; label: string }[] = [
  { id: "questions", label: "Questions" },
  { id: "retrieval", label: "Retrieval" },
  { id: "chunking", label: "Chunking" },
  { id: "history", label: "Chat history" },
  { id: "model", label: "Model" },
];

export function ResultsScreen() {
  const { runId = "" } = useParams();
  const results = useResults(runId);
  const rows = results.metrics?.rows ?? [];
  const primary = results.traces.filter((trace) => trace.kind === "primary");
  const cited = primary.filter((trace) => citedPassages(trace).length > 0).length;
  if (results.loading) {
    return <LoadingSkeleton variant="results" />;
  }
  if (results.error) {
    return <ErrorState message={results.error} onRetry={results.retry} />;
  }
  if (!results.traces.length) {
    return <EmptyState title="No traces yet" body="The run has no traces yet." />;
  }
  return (
    <section>
      <PageHead title="Results" body={`${results.traces.length} stored traces`} />
      <ScoreCards summary={results.metrics?.summary.metrics ?? {}} />
      <RunFacts summary={results.metrics?.summary.metrics ?? {}} answers={primary.length} cited={cited} />
      <div className="tabs" role="tablist" aria-label="Result views" onKeyDown={(event) => moveTab(event, results.tab, results.setResultsTab)}>
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            id={`tab-${tab.id}`}
            aria-selected={results.tab === tab.id}
            aria-controls={`panel-${tab.id}`}
            className="tab"
            tabIndex={results.tab === tab.id ? 0 : -1}
            onClick={() => results.setResultsTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`panel-${results.tab}`} aria-labelledby={`tab-${results.tab}`}>
        {results.tab === "questions" ? (
          <div className="card scroll">
            <QuestionTable
              rows={results.traces
                .filter((trace) => trace.kind === "primary")
                .map((trace) => ({
                  testCaseId: trace.test_case_id,
                  question: trace.question,
                  answer: trace.answer ?? trace.error ?? "",
                  status: trace.status,
                  correctness: rows.find((row) => row.test_case_id === trace.test_case_id && row.metric_id === "correctness"),
                  faithfulness: rows.find((row) => row.test_case_id === trace.test_case_id && row.metric_id === "faithfulness"),
                }))}
            />
          </div>
        ) : null}
        {results.tab === "retrieval" ? (
          <div className="card scroll">
            <RetrievalTable
              rows={primary.map((trace) => ({
                question: trace.question,
                passages: citedPassages(trace),
                latencyMs: trace.latency_ms,
                promptTokens: trace.prompt_tokens,
                completionTokens: trace.completion_tokens,
              }))}
            />
            <p className="hint" style={{ marginTop: 12 }}>
              Hit rate, precision, recall, and MRR need a source passage on each dataset row. The passages above are the sources the answers cited.
            </p>
          </div>
        ) : null}
        {results.tab === "chunking" ? (
          <div className="card scroll" style={{ marginBottom: 18 }}>
            <h2>Passages cited in the answers</h2>
            <p className="hint">{cited} of {primary.length} answers named a source.</p>
            <table>
              <thead>
                <tr>
                  <th>Question</th>
                  <th>Source</th>
                  <th>Citation</th>
                </tr>
              </thead>
              <tbody>
                {primary.map((trace) => {
                  const passages = citedPassages(trace);
                  return (
                    <tr key={trace.id}>
                      <td>{trace.question}</td>
                      <td>{passages.map((chunk) => chunk.source).filter(Boolean).join(", ") || "—"}</td>
                      <td>{passages.map((chunk) => chunk.text).join(" ") || "No source cited"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : null}
        {results.tab === "history" ? (
          <div className="card scroll" style={{ marginBottom: 18 }}>
            <h2>Questions in this run</h2>
            <p className="hint">
              {primary.some((trace) => trace.turn_index > 0)
                ? "Follow-up turns are scored for history."
                : "Every question was asked on its own, so there is no follow-up score."}
            </p>
            <table>
              <thead>
                <tr>
                  <th>Question</th>
                  <th>Answer</th>
                  <th>Latency</th>
                </tr>
              </thead>
              <tbody>
                {primary.map((trace) => (
                  <tr key={trace.id}>
                    <td>{trace.question}</td>
                    <td>{trace.answer ?? trace.error ?? ""}</td>
                    <td>{formatDuration(trace.latency_ms)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
        {results.tab === "model" ? (
          <div className="card scroll">
            <ModelCostTable summary={results.metrics?.summary.metrics ?? {}} />
          </div>
        ) : null}
      </div>
    </section>
  );
}

function moveTab(event: KeyboardEvent, current: ResultsTab, setTab: (tab: ResultsTab) => void) {
  const index = TABS.findIndex((tab) => tab.id === current);
  if (event.key === "ArrowRight") {
    setTab(TABS[(index + 1) % TABS.length].id);
  }
  if (event.key === "ArrowLeft") {
    setTab(TABS[(index - 1 + TABS.length) % TABS.length].id);
  }
}
