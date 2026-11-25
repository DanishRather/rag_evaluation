import type { ReactNode } from "react";

import type { ProbeSummary, ThemeMode } from "../../model/types";

export function AppShell({
  children,
  nav,
  onToggleTheme,
  theme,
  projectName,
  systemName,
  endpointUrl,
  probe,
  lastRunId,
}: {
  children: ReactNode;
  nav: ReactNode;
  onToggleTheme: (mode: ThemeMode) => void;
  theme: ThemeMode;
  projectName: string;
  systemName: string;
  endpointUrl: string;
  probe: ProbeSummary | null;
  lastRunId: string | null;
}) {
  return (
    <div className="shell">
      <a className="skip" href="#main">
        Skip to content
      </a>
      <nav className="side" aria-label="Main">
        <div className="logo">
          RAG Evaluator
          <small>Judge-agent test bench</small>
        </div>
        {nav}
        <div className="foot">
          <div>Project: {projectName || "not connected"}</div>
          <div>System: {systemName || "not connected"}</div>
          {endpointUrl ? (
            <div className="endpoint" title={endpointUrl}>
              <code>{endpointUrl}</code>
            </div>
          ) : null}
          {endpointUrl ? (
            <div>
              Last test:{" "}
              {probe ? <span className={probe.ok ? "tag t-good" : "tag t-bad"}>{probe.ok ? "answered" : "failed"}</span> : "not tested"}
            </div>
          ) : null}
          <div>Last run: {lastRunId ? lastRunId.slice(0, 8) : "not run yet"}</div>
          <ThemeToggle mode={theme} onChange={onToggleTheme} />
        </div>
      </nav>
      <main id="main">{children}</main>
    </div>
  );
}

export function PageHead({ title, body }: { title: string; body: string }) {
  return (
    <div className="head">
      <h1>{title}</h1>
      <p>{body}</p>
    </div>
  );
}

export function ThemeToggle({ mode, onChange }: { mode: ThemeMode; onChange: (mode: ThemeMode) => void }) {
  return (
    <fieldset className="theme">
      <legend>Theme</legend>
      {(["system", "light", "dark"] as ThemeMode[]).map((item) => (
        <label key={item}>
          <input type="radio" name="theme" value={item} checked={mode === item} onChange={() => onChange(item)} />
          {item}
        </label>
      ))}
    </fieldset>
  );
}

export function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="state" role="status">
      <h2>{title}</h2>
      <p>{body}</p>
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="state error" role="alert">
      <h2>Something went wrong</h2>
      <p>{message}</p>
      {onRetry ? (
        <button type="button" onClick={onRetry}>
          Retry
        </button>
      ) : null}
    </div>
  );
}

export function LoadingSkeleton({ variant }: { variant: string }) {
  return (
    <div className="skeleton" aria-busy="true" aria-live="polite">
      Loading {variant}
    </div>
  );
}
