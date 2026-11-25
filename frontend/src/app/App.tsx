import { NavLink, Route, Routes, useLocation } from "react-router-dom";

import { ConnectSystemScreen } from "../controller/screens/ConnectSystemScreen";
import { DatasetScreen } from "../controller/screens/DatasetScreen";
import { JudgeRunScreen } from "../controller/screens/JudgeRunScreen";
import { ResultsScreen } from "../controller/screens/ResultsScreen";
import { SetupReportScreen } from "../controller/screens/SetupReportScreen";
import { applyTheme, useUiStore } from "../model/stores/ui";
import { AppShell } from "../view/components/Chrome";

const STEPS = [
  ["1", "/connect", "Connect system"],
  ["2", "/dataset", "Test dataset"],
  ["3", "/run", "Judge & run"],
] as const;

export function App() {
  const theme = useUiStore((state) => state.theme);
  const setTheme = useUiStore((state) => state.setTheme);
  const projectName = useUiStore((state) => state.projectName);
  const systemName = useUiStore((state) => state.systemName);
  const endpointUrl = useUiStore((state) => state.endpointUrl);
  const configId = useUiStore((state) => state.configId);
  const probes = useUiStore((state) => state.probes);
  const lastRunId = useUiStore((state) => state.lastRunId);
  const location = useLocation();
  const routeRun = location.pathname.match(/^\/runs\/([^/]+)/)?.[1] ?? null;
  const runId = routeRun || lastRunId;
  applyTheme(theme);
  return (
    <AppShell
      theme={theme}
      onToggleTheme={setTheme}
      projectName={projectName}
      systemName={systemName}
      endpointUrl={endpointUrl}
      probe={configId ? (probes[configId] ?? null) : null}
      lastRunId={runId}
      nav={<PrimaryNav runId={runId} />}
    >
      <Routes>
        <Route path="/" element={<ConnectSystemScreen />} />
        <Route path="/connect" element={<ConnectSystemScreen />} />
        <Route path="/dataset" element={<DatasetScreen />} />
        <Route path="/run" element={<JudgeRunScreen />} />
        <Route path="/runs/:runId/results" element={<ResultsScreen />} />
        <Route path="/runs/:runId/report" element={<SetupReportScreen />} />
      </Routes>
    </AppShell>
  );
}

function PrimaryNav({ runId }: { runId: string | null }) {
  return (
    <>
      {STEPS.map(([number, to, label]) => (
        <NavLink key={to} to={to} className={({ isActive }) => (isActive ? "nav on" : "nav")}>
          <i>{number}</i>
          {label}
        </NavLink>
      ))}
      <RunLink number="4" runId={runId} suffix="results" label="Results" />
      <RunLink number="5" runId={runId} suffix="report" label="Setup report" />
    </>
  );
}

function RunLink({ number, runId, suffix, label }: { number: string; runId: string | null; suffix: string; label: string }) {
  if (!runId) {
    return (
      <span className="nav" aria-disabled="true">
        <i>{number}</i>
        {label}
      </span>
    );
  }
  return (
    <NavLink to={`/runs/${runId}/${suffix}`} className={({ isActive }) => (isActive ? "nav on" : "nav")}>
      <i>{number}</i>
      {label}
    </NavLink>
  );
}
