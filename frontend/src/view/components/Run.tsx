import { Link } from "react-router-dom";

import type { Dataset, Estimate, LiveItem, LiveState, ProbeSummary, Run, RunLive } from "../../model/types";
import { formatTime, ProbeTag } from "./Connect";

const LABELS: Record<string, string> = {
  correctness: "Correctness",
  faithfulness: "Faithfulness",
  usefulness_worst_case: "Usefulness, worst case",
  split_confirm_worst_case: "Split confirm, worst case",
  rewrite: "Rewrite",
  report_writer: "Report writer",
};

const RUN_STATUS: Record<string, [string, string]> = {
  queued: ["Queued", "t-n"],
  running: ["Running", "t-warn"],
  cancel_requested: ["Stopping", "t-warn"],
  succeeded: ["Finished", "t-good"],
  failed: ["Failed", "t-bad"],
  cancelled: ["Cancelled", "t-n"],
};

const ITEM_STATE: Record<LiveState, [string, string]> = {
  queued: ["Queued", "t-n"],
  calling: ["Calling endpoint", "t-warn"],
  judging: ["Judging", "t-warn"],
  done: ["Done", "t-good"],
  failed: ["Failed", "t-bad"],
  not_run: ["Not run", "t-n"],
  stopped: ["Stopped", "t-n"],
};

export function EstimateBanner({ estimate }: { estimate: Estimate | null }) {
  if (!estimate) {
    return null;
  }
  return (
    <section className="card" style={{ marginTop: 18 }} aria-label="Estimate">
      <h2>Estimate</h2>
      <p>
        Target calls {estimate.target_calls}. Extra counterfactual calls {estimate.counterfactual_calls}.
      </p>
      <table>
        <caption>Judge calls</caption>
        <thead>
          <tr>
            <th>Check</th>
            <th>Calls</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(estimate.judge_calls).map(([key, count]) => (
            <tr key={key}>
              <td>{LABELS[key] ?? key}</td>
              <td>{count}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <ul>
        {estimate.notes.map((note) => (
          <li key={note}>{note}</li>
        ))}
      </ul>
    </section>
  );
}

export function RunControls({
  canStart,
  status,
  starting,
  onStart,
  onCancel,
  onResume,
  onReevaluate,
  onEstimate,
}: {
  canStart: boolean;
  status: string;
  starting: boolean;
  onStart: () => void;
  onCancel: () => void;
  onResume: () => void;
  onReevaluate: () => void;
  onEstimate: () => void;
}) {
  const canCancel = status === "queued" || status === "running" || status === "cancel_requested";
  const canResume = status === "failed" || status === "cancelled";
  const canReevaluate = status === "succeeded" || status === "failed" || status === "cancelled";
  return (
    <div>
      <div className="actions">
        <button className="btn" type="button" onClick={onEstimate} disabled={!canStart}>
          Estimate
        </button>
        <button className="btn p" type="button" onClick={onStart} disabled={!canStart || starting}>
          {starting ? "Starting…" : "Run evaluation"}
        </button>
        <button className="btn" type="button" onClick={onCancel} disabled={!canCancel}>
          Cancel
        </button>
        <button className="btn" type="button" onClick={onResume} disabled={!canResume}>
          Resume
        </button>
        <button className="btn" type="button" onClick={onReevaluate} disabled={!canReevaluate}>
          Re-evaluate
        </button>
      </div>
      <p className="hint">
        Cancel stops a run that is queued or still calling the endpoint. Resume continues that same connection, so it cannot
        repair a connection that sent a fixed text. Re-evaluate judges answers already stored and does not call the endpoint again.
      </p>
    </div>
  );
}

export function RunTarget({
  connected,
  systemName,
  url,
  encoding,
  probe,
  dataset,
}: {
  connected: boolean;
  systemName: string;
  url: string;
  encoding: string;
  probe: ProbeSummary | null;
  dataset: Dataset | null;
}) {
  return (
    <div className="grid g2" style={{ marginBottom: 18 }}>
      <div className="card" aria-label="Endpoint">
        <h2>
          Endpoint {connected ? <ProbeTag probe={probe} /> : <span className="tag t-bad">Not connected</span>}
        </h2>
        {connected ? (
          <>
            <p>
              <b>{systemName}</b>
            </p>
            <p className="endpoint">
              <code>POST {url}</code>
            </p>
            <p className="hint">
              {encoding === "form" ? "Form fields" : "JSON body"}
              {probe ? ` · last test ${formatTime(probe.at)}` : ""}
            </p>
          </>
        ) : (
          <p className="hint">Connect a system before you start a run.</p>
        )}
        <div className="actions">
          <Link className="btn s" to="/connect">
            {connected ? "Change endpoint" : "Connect a system"}
          </Link>
        </div>
      </div>
      <div className="card" aria-label="Dataset">
        <h2>Dataset {dataset ? <span className="tag t-good">{dataset.case_count} questions</span> : <span className="tag t-bad">None</span>}</h2>
        {dataset ? (
          <p>
            <b>{dataset.source_filename}</b>
            {dataset.needs_mapping ? <span className="tag t-bad"> Map the question column first</span> : null}
          </p>
        ) : (
          <p className="hint">Upload a file with a question column.</p>
        )}
        <div className="actions">
          <Link className="btn s" to="/dataset">
            {dataset ? "Change file" : "Upload a file"}
          </Link>
        </div>
      </div>
    </div>
  );
}

export function LiveRunPanel({ live, now, error }: { live: RunLive | null; now: number; error: string }) {
  if (!live) {
    return (
      <section className="card" style={{ marginTop: 18 }} aria-label="Live run">
        <h2>Live run</h2>
        <p className={error ? "error-text" : "hint"}>{error || "Start a run to watch each question go to your endpoint."}</p>
      </section>
    );
  }
  const computed = live.done + live.failed;
  const percent = live.total ? Math.round((computed / live.total) * 100) : 0;
  const current = live.items.filter((item) => item.state === "calling" || item.state === "judging");
  const next = live.items.filter((item) => item.state === "queued").slice(0, 5);
  const finished = live.items
    .filter((item) => item.state === "done" || item.state === "failed")
    .sort((a, b) => (b.finished_at ?? "").localeCompare(a.finished_at ?? ""))
    .slice(0, 8);
  const [label, tone] = RUN_STATUS[live.status] ?? [live.status, "t-n"];
  return (
    <section className="card live" style={{ marginTop: 18 }} aria-label="Live run">
      <div className="live-head">
        <h2>
          Live run <span className={`tag ${tone}`}>{label}</span>
        </h2>
        <span className="hint">
          Run {live.run_id.slice(0, 8)} · {live.max_concurrency} at a time · endpoint timeout {live.target_timeout_s}s
        </span>
      </div>
      <div className="bar" aria-hidden="true">
        <b style={{ width: `${percent}%` }} />
      </div>
      <p className="hint" aria-live="polite">
        {computed} of {live.total} questions computed ({percent}%)
      </p>
      <div className="grid g5 stats">
        <Stat value={live.total} label="Total questions" />
        <Stat value={live.done} label="Computed" />
        <Stat value={live.failed} label="Failed" />
        <Stat value={live.running} label="Running now" />
        <Stat value={live.remaining} label="Still to compute" />
      </div>
      <StatusNotice live={live} />
      <h3>Now running</h3>
      {current.length ? (
        <div className="scroll">
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>Question</th>
                <th>Step</th>
                <th>Waiting</th>
              </tr>
            </thead>
            <tbody>
              {current.map((item) => (
                <tr key={`${item.test_case_id}-${item.repeat_index}`}>
                  <td>{item.position}</td>
                  <td className="q">{item.question}</td>
                  <td>
                    <span className={`tag ${ITEM_STATE[item.state][1]}`}>{stageLabel(item)}</span>
                    {item.attempt && item.attempt > 1 ? (
                      <div className="hint">
                        Attempt {item.attempt} of {item.max_attempts}
                        {item.last_error ? ` · last error: ${item.last_error}` : ""}
                      </div>
                    ) : null}
                  </td>
                  <td>{elapsed(item.stage_started_at, now)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="hint">{live.status === "running" && live.remaining === 0 ? "All questions are computed. Writing the report…" : "Nothing is running right now."}</p>
      )}
      <h3>Up next</h3>
      {next.length ? (
        <ol className="queue">
          {next.map((item) => (
            <li key={`${item.test_case_id}-${item.repeat_index}`} value={item.position}>
              {item.question}
              {item.repeat_index > 0 ? <span className="hint"> · repeat {item.repeat_index + 1}</span> : null}
            </li>
          ))}
          {live.waiting > next.length ? <li className="hint more">and {live.waiting - next.length} more</li> : null}
        </ol>
      ) : (
        <p className="hint">No questions are waiting.</p>
      )}
      <h3>Just finished</h3>
      {finished.length ? <ItemTable items={finished} /> : <p className="hint">No question has finished yet.</p>}
      <details>
        <summary>All questions ({live.total})</summary>
        <ItemTable items={live.items} />
      </details>
      <details>
        <summary>Event log</summary>
        <div className="log">
          {live.log.length
            ? live.log.map((entry) => `${formatTime(entry.at)}  ${entry.kind}: ${entry.message}`).join("\n")
            : "No events yet."}
        </div>
      </details>
    </section>
  );
}

function StatusNotice({ live }: { live: RunLive }) {
  if (live.status === "failed") {
    return <p className="notice bad">{live.message || "Run failed."}</p>;
  }
  if (live.status === "cancel_requested") {
    return <p className="notice">Stopping after the questions that are already running finish.</p>;
  }
  if (live.status !== "queued") {
    return null;
  }
  if (!live.worker.embedded) {
    return (
      <p className="notice">
        This API does not run jobs because EVAL_EMBEDDED_WORKER=0. Start the worker with <code>uv run --env-file .env eval-worker</code>.
      </p>
    );
  }
  if (!live.worker.alive) {
    return <p className="notice bad">The worker inside the API stopped. Restart the API with uv run main.py.</p>;
  }
  if (live.runs_ahead > 0) {
    return (
      <p className="notice">
        Waiting behind {live.runs_ahead} other {live.runs_ahead === 1 ? "run" : "runs"}. Runs go one at a time. Cancel older runs
        in Recent runs if you do not need them.
      </p>
    );
  }
  return <p className="notice info">Waiting for the worker to pick up this run…</p>;
}

function ItemTable({ items }: { items: LiveItem[] }) {
  return (
    <div className="scroll">
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Question</th>
            <th>Status</th>
            <th>Endpoint time</th>
            <th>Answer or error</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={`${item.test_case_id}-${item.repeat_index}`}>
              <td>{item.position}</td>
              <td className="q">{item.question}</td>
              <td>
                <span className={`tag ${ITEM_STATE[item.state][1]}`}>{ITEM_STATE[item.state][0]}</span>
                {item.cause ? <div className="hint">{item.cause}</div> : null}
              </td>
              <td>{item.latency_ms == null ? "" : `${(item.latency_ms / 1000).toFixed(1)}s`}</td>
              <td className="q">
                {item.error ? <span className="error-text">{item.error}</span> : <span className="hint">{item.answer ?? ""}</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function RecentRuns({
  runs,
  activeRunId,
  onWatch,
  onDelete,
  onClearFailed,
  clearing,
}: {
  runs: Run[];
  activeRunId: string | null;
  onWatch: (runId: string) => void;
  onDelete: (runId: string) => void;
  onClearFailed: () => void;
  clearing: boolean;
}) {
  if (!runs.length) {
    return null;
  }
  return (
    <div className="card scroll" style={{ marginTop: 18 }}>
      <h2>Recent runs</h2>
      {runs.some((run) => run.status === "failed" || run.status === "cancelled") ? (
        <div className="actions">
          <button className="btn s" type="button" onClick={onClearFailed} disabled={clearing}>
            {clearing ? "Clearing…" : "Clear failed runs"}
          </button>
        </div>
      ) : null}
      <table>
        <thead>
          <tr>
            <th>Started</th>
            <th>Run</th>
            <th>Status</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => {
            const [label, tone] = RUN_STATUS[run.status] ?? [run.status, "t-n"];
            const watching = run.id === activeRunId;
            return (
              <tr key={run.id} className={watching ? "on" : undefined}>
                <td>{new Date(run.created_at).toLocaleString()}</td>
                <td>
                  <code>{run.id.slice(0, 8)}</code>
                </td>
                <td>
                  <span className={`tag ${tone}`}>{label}</span>
                </td>
                <td>
                  <div className="actions" style={{ marginTop: 0 }}>
                    {watching ? (
                      <span className="tag t-good">Watching</span>
                    ) : (
                      <button className="btn s" type="button" onClick={() => onWatch(run.id)}>
                        Watch
                      </button>
                    )}
                    {run.status === "failed" || run.status === "cancelled" || run.status === "succeeded" ? (
                      <button className="btn s" type="button" onClick={() => onDelete(run.id)}>
                        Delete
                      </button>
                    ) : null}
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Stat({ value, label }: { value: number; label: string }) {
  return (
    <div className="stat">
      <div className="n">{value}</div>
      <div className="l">{label}</div>
    </div>
  );
}

function stageLabel(item: LiveItem) {
  if (item.state === "judging") {
    return "Judge is scoring the answer";
  }
  if (item.stage === "counterfactual") {
    return "Calling endpoint with the standalone rewrite";
  }
  return "Waiting for the endpoint answer";
}

function elapsed(iso: string | null, now: number) {
  if (!iso) {
    return "";
  }
  const started = new Date(iso).getTime();
  if (Number.isNaN(started)) {
    return "";
  }
  const seconds = Math.max(0, Math.round((now - started) / 1000));
  if (seconds < 60) {
    return `${seconds}s`;
  }
  return `${Math.floor(seconds / 60)}m ${String(seconds % 60).padStart(2, "0")}s`;
}
