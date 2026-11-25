import type { Connection, ProbeResult, ProbeSummary, SystemDraft } from "../../model/types";

const EMPTY: SystemDraft = {
  projectName: "",
  systemName: "",
  url: "http://127.0.0.1:8000/agents/query-agent/runs",
  requestTemplate: "message={{ question }}",
  answerPath: "$.content",
  encoding: "form",
  testQuery: "",
};

export const emptySystemDraft = EMPTY;

export const PRESETS: { id: string; label: string; values: Pick<SystemDraft, "encoding" | "requestTemplate" | "answerPath"> }[] = [
  {
    id: "agno",
    label: "Agno AgentOS run (form: message)",
    values: { encoding: "form", requestTemplate: "message={{ question }}", answerPath: "$.content" },
  },
  {
    id: "json",
    label: "JSON: question field",
    values: { encoding: "json", requestTemplate: '{"question": {{ question | tojson }}}', answerPath: "$.answer" },
  },
];

const QUESTION_PLACEHOLDER = /\{\{[^}]*\bquestion\b[^}]*\}\}/;

export function SystemForm({
  value,
  onChange,
  onSubmit,
  disabled,
  error,
}: {
  value: SystemDraft;
  onChange: (value: SystemDraft) => void;
  onSubmit: () => void;
  disabled: boolean;
  error?: string;
}) {
  function set<K extends keyof SystemDraft>(key: K, next: SystemDraft[K]) {
    onChange({ ...value, [key]: next });
  }
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <div className="card">
        <h2>Endpoint</h2>
        <div className="presets" aria-label="Presets">
          <span className="hint">Fill from a preset:</span>
          {PRESETS.map((preset) => (
            <button key={preset.id} className="btn s" type="button" onClick={() => onChange({ ...value, ...preset.values })}>
              {preset.label}
            </button>
          ))}
        </div>
        <div className="row">
          <Field label="Project name" value={value.projectName} onChange={(next) => set("projectName", next)} />
          <Field label="System name" value={value.systemName} onChange={(next) => set("systemName", next)} />
        </div>
        <Field label="Endpoint URL" value={value.url} onChange={(next) => set("url", next)} />
        <label>
          Body format
          <select
            value={value.encoding ?? "json"}
            onChange={(event) => {
              const encoding = event.target.value as "json" | "form";
              const preset = PRESETS.find((item) => item.values.encoding === encoding);
              onChange({ ...value, encoding, ...(preset?.values ?? {}) });
            }}
          >
            <option value="json">JSON</option>
            <option value="form">Form fields (like curl -F)</option>
          </select>
        </label>
        <label>
          Query to test
          <textarea
            className="query"
            value={value.testQuery}
            onChange={(event) => set("testQuery", event.target.value)}
            placeholder="What does Article 10.7 of the KG-D6 PSC say?"
          />
        </label>
        <p className="hint">
          Plain text. The test sends this query once. A run sends each question from your file the same way, so you do not write
          the JSON.
        </p>
        <Field label="Answer text path" value={value.answerPath} onChange={(next) => set("answerPath", next)} />
        {error ? (
          <p id="connect-error" className="error-text">
            {error}
          </p>
        ) : null}
        <div className="actions">
          <button className="btn p" type="submit" disabled={disabled}>
            {disabled ? "Testing…" : "Save and test connection"}
          </button>
          <span className="hint">Saves a new version of this system, then sends one sample question</span>
        </div>
      </div>
    </form>
  );
}

function Field({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <label>
      {label}
      <input value={value} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

export function ProbeResultView({ probe, query }: { probe: ProbeResult | null; query?: string }) {
  if (!probe) {
    return null;
  }
  const failed = Boolean(probe.error) || !probe.answer;
  return (
    <div className="card" style={{ marginTop: 18 }}>
      <h2>
        Sample answer <span className={failed ? "tag t-bad" : "tag t-good"}>{failed ? "Failed" : "Answer received"}</span>
      </h2>
      {query?.trim() ? <p className="hint">Query: {query.trim()}</p> : null}
      {probe.error ? (
        <p className="error-text">{probe.error}</p>
      ) : (
        <p>{probe.answer || "The endpoint answered, but the answer text path found nothing."}</p>
      )}
    </div>
  );
}

export function ProbeTag({ probe }: { probe: ProbeSummary | null }) {
  if (!probe) {
    return <span className="tag t-n">Not tested</span>;
  }
  return <span className={probe.ok ? "tag t-good" : "tag t-bad"}>{probe.ok ? "Answered" : "Failed"}</span>;
}

export function ActiveConnection({ connection, probe }: { connection: Connection | null; probe: ProbeSummary | null }) {
  if (!connection) {
    return (
      <div className="notice info" role="status">
        No endpoint is in use yet. Fill the form and test it, or pick a saved connection below.
      </div>
    );
  }
  const settings = connection.config.adapter_settings;
  return (
    <div className="card" style={{ marginBottom: 18 }} aria-label="Endpoint in use">
      <h2>
        In use: {connection.system_name} <ProbeTag probe={probe} />
      </h2>
      <p className="endpoint">
        <code>POST {String(settings.url ?? "")}</code>
      </p>
      <p className="hint">
        Project {connection.project_name} · {settings.encoding === "form" ? "form fields" : "JSON body"} · answer at{" "}
        {String((settings.response_map as Record<string, unknown> | undefined)?.answer ?? "$.answer")} · version{" "}
        {connection.config.version}
        {probe ? ` · last test ${formatTime(probe.at)}: ${probe.message}` : ""}
      </p>
    </div>
  );
}

export function ConnectionList({
  connections,
  activeConfigId,
  probes,
  testingId,
  onUse,
  onTest,
  onDelete,
  onClearBroken,
  clearing,
}: {
  connections: Connection[];
  activeConfigId: string | null;
  probes: Record<string, ProbeSummary>;
  testingId: string | null;
  onUse: (connection: Connection) => void;
  onTest: (configId: string) => void;
  onDelete: (systemId: string) => void;
  onClearBroken: () => void;
  clearing: boolean;
}) {
  if (!connections.length) {
    return null;
  }
  return (
    <div className="card scroll" style={{ marginTop: 18 }}>
      <h2>Saved connections</h2>
      <p className="hint">Runs call the connection that is in use. Test sends the query typed above.</p>
      {connections.some((connection) => !QUESTION_PLACEHOLDER.test(String(connection.config.adapter_settings.request_template ?? ""))) ? (
        <div className="actions">
          <button className="btn s" type="button" onClick={onClearBroken} disabled={clearing}>
            {clearing ? "Clearing…" : "Clear connections that send a fixed question"}
          </button>
        </div>
      ) : null}
      <table>
        <thead>
          <tr>
            <th>System</th>
            <th>Endpoint</th>
            <th>Last test</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {connections.map((connection) => {
            const settings = connection.config.adapter_settings;
            const template = String(settings.request_template ?? "");
            const active = connection.config.id === activeConfigId;
            const probe = probes[connection.config.id] ?? null;
            return (
              <tr key={connection.config.id} className={active ? "on" : undefined}>
                <td>
                  <b>{connection.system_name}</b>
                  <br />
                  <span className="hint">
                    {connection.project_name} · v{connection.config.version}
                  </span>
                </td>
                <td className="endpoint">
                  <code>{String(settings.url ?? "")}</code>
                  <br />
                  <span className="hint">{settings.encoding === "form" ? "Form fields" : "JSON"}</span>{" "}
                  {template && !QUESTION_PLACEHOLDER.test(template) ? <span className="tag t-bad">Sends a fixed question</span> : null}
                </td>
                <td>
                  <ProbeTag probe={probe} />
                  {probe ? <div className="hint">{formatTime(probe.at)}</div> : null}
                </td>
                <td>
                  <div className="actions" style={{ marginTop: 0 }}>
                    {active ? (
                      <span className="tag t-good">In use</span>
                    ) : (
                      <button className="btn s" type="button" onClick={() => onUse(connection)}>
                        Use
                      </button>
                    )}
                    <button
                      className="btn s"
                      type="button"
                      onClick={() => onTest(connection.config.id)}
                      disabled={testingId === connection.config.id}
                    >
                      {testingId === connection.config.id ? "Testing…" : "Test"}
                    </button>
                    {!QUESTION_PLACEHOLDER.test(template) ? (
                      <button className="btn s" type="button" onClick={() => onDelete(connection.system_id)}>
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

export function formatTime(iso: string | null | undefined) {
  if (!iso) {
    return "";
  }
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleTimeString();
}
