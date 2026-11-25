import { Link } from "react-router-dom";

import { ErrorState, PageHead } from "../../view/components/Chrome";
import { EstimateBanner, LiveRunPanel, RecentRuns, RunControls, RunTarget } from "../../view/components/Run";
import { useRecentRuns, useRunControl, useRunLive, useRunTarget } from "../hooks/useRunControl";

const CHECKS = [
  ["quality", "Answer quality", "Correctness and faithfulness"],
  ["retrieval", "Retrieval", "Hit rate, precision, recall, and MRR"],
  ["chunking", "Chunking", "Split answers, chunk size, and overlap"],
  ["history", "Chat-history reasoning", "Follow-ups and standalone rewrites"],
  ["model", "Model and cost", "Latency, tokens, and cost per answer"],
] as const;

export function JudgeRunScreen() {
  const control = useRunControl();
  const target = useRunTarget();
  const live = useRunLive(control.runId);
  const recent = useRecentRuns();
  return (
    <section>
      <PageHead
        title="Judge and run"
        body="Every dataset question goes to the endpoint below, then the judge scores the answer. The judge instructions are fixed. The judge model and key come from the environment."
      />
      <RunTarget
        connected={target.connected}
        systemName={target.systemName}
        url={target.url}
        encoding={target.encoding}
        probe={target.probe}
        dataset={target.dataset}
      />
      {target.connected && !target.sendsQuestions ? (
        <p className="notice bad">
          The connection in use sends one fixed text, not the questions from the file. Open Connect, save it again, and click Use
          on that saved connection before you start a run.
        </p>
      ) : null}
      <div className="grid g2">
        <div className="card">
          <h2>What to evaluate</h2>
          {CHECKS.map(([key, title, hint]) => (
            <label className="chk" key={key}>
              <input
                type="checkbox"
                checked={control.checks[key]}
                onChange={(event) => control.setChecks({ ...control.checks, [key]: event.target.checked })}
              />
              <span>
                <b>{title}</b>
                <br />
                <span className="hint">{hint}</span>
              </span>
            </label>
          ))}
        </div>
        <div className="card">
          <h2>Judge settings</h2>
          <label>
            Provider
            <select value={control.provider} onChange={(event) => control.setProvider(event.target.value as "openai_chat" | "openai_responses")}>
              <option value="openai_chat">OpenAI chat</option>
              <option value="openai_responses">OpenAI responses</option>
            </select>
          </label>
          <label>
            Judge model
            <input value={control.modelId} onChange={(event) => control.setModelId(event.target.value)} placeholder="From EVAL_JUDGE_MODEL" />
          </label>
          <label>
            Secondary model
            <input value={control.secondaryModel} onChange={(event) => control.setSecondaryModel(event.target.value)} placeholder="Optional second judge" />
          </label>
          <div className="row">
            <label>
              Repeats per question
              <input type="number" min={1} value={control.repeats} onChange={(event) => control.setRepeats(Number(event.target.value) || 1)} />
            </label>
            <label>
              Questions at a time
              <input type="number" min={1} value={control.maxConcurrency} onChange={(event) => control.setMaxConcurrency(Number(event.target.value) || 1)} />
            </label>
          </div>
          <div className="row">
            <label>
              Endpoint timeout (seconds)
              <input type="number" min={5} value={control.targetTimeout} onChange={(event) => control.setTargetTimeout(Number(event.target.value) || 180)} />
            </label>
            <label>
              Attempts per question
              <input type="number" min={1} value={control.targetAttempts} onChange={(event) => control.setTargetAttempts(Number(event.target.value) || 1)} />
            </label>
          </div>
          <p className="hint">A local model answers one question at a time. Keep questions at a time at 1 unless the endpoint handles parallel calls.</p>
          <RunControls
            canStart={control.canStart && target.sendsQuestions}
            status={live.live?.status ?? ""}
            starting={control.starting}
            onEstimate={control.requestEstimate}
            onStart={control.startRun}
            onCancel={control.cancelRun}
            onResume={control.resumeRun}
            onReevaluate={control.reevaluateRun}
          />
          {!Object.values(control.checks).some(Boolean) ? <p className="hint">Select at least one check.</p> : null}
          {!control.canStart && Object.values(control.checks).some(Boolean) ? (
            <p className="hint">Choose a dataset and a system. The judge model comes from EVAL_JUDGE_MODEL unless you type one.</p>
          ) : null}
        </div>
      </div>
      <EstimateBanner estimate={control.estimate} />
      {control.error ? <ErrorState message={control.error} /> : null}
      <LiveRunPanel live={live.live} now={live.now} error={live.error} />
      {control.runId ? (
        <div className="actions">
          <Link className="btn p" to={`/runs/${control.runId}/results`}>
            Open results
          </Link>
        </div>
      ) : null}
      <RecentRuns
        runs={recent.runs}
        activeRunId={control.runId}
        onWatch={control.watchRun}
        onDelete={control.deleteRun}
        onClearFailed={control.clearFailedRuns}
        clearing={control.clearing}
      />
    </section>
  );
}
