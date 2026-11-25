import { create } from "zustand";

import type { ProbeSummary, ResultsTab, ThemeMode } from "../types";

export type { ResultsTab, ThemeMode };

const THEME_KEY = "eval-theme";
const WORKSPACE_KEY = "eval-workspace";

function storedTheme(): ThemeMode {
  const value = localStorage.getItem(THEME_KEY);
  if (value === "light" || value === "dark" || value === "system") {
    return value;
  }
  return "system";
}

interface Workspace {
  projectId: string | null;
  systemId: string | null;
  configId: string | null;
  datasetId: string | null;
  projectName: string;
  systemName: string;
  endpointUrl: string;
  lastRunId: string | null;
  probes: Record<string, ProbeSummary>;
}

const EMPTY_WORKSPACE: Workspace = {
  projectId: null,
  systemId: null,
  configId: null,
  datasetId: null,
  projectName: "",
  systemName: "",
  endpointUrl: "",
  lastRunId: null,
  probes: {},
};

function storedWorkspace(): Workspace {
  try {
    const raw = localStorage.getItem(WORKSPACE_KEY);
    if (raw) {
      return { ...EMPTY_WORKSPACE, ...(JSON.parse(raw) as Partial<Workspace>) };
    }
  } catch {
    return EMPTY_WORKSPACE;
  }
  return EMPTY_WORKSPACE;
}

function persist(state: Workspace) {
  const snapshot: Workspace = {
    projectId: state.projectId,
    systemId: state.systemId,
    configId: state.configId,
    datasetId: state.datasetId,
    projectName: state.projectName,
    systemName: state.systemName,
    endpointUrl: state.endpointUrl,
    lastRunId: state.lastRunId,
    probes: state.probes,
  };
  localStorage.setItem(WORKSPACE_KEY, JSON.stringify(snapshot));
}

type WorkspacePatch = Partial<
  Pick<Workspace, "projectId" | "systemId" | "configId" | "datasetId" | "projectName" | "systemName" | "endpointUrl">
>;

interface UiState extends Workspace {
  theme: ThemeMode;
  setTheme: (theme: ThemeMode) => void;
  resultsTab: ResultsTab;
  setResultsTab: (tab: ResultsTab) => void;
  columnDraft: Record<string, string>;
  setColumnDraft: (draft: Record<string, string>) => void;
  clearColumnDraft: () => void;
  setWorkspace: (patch: WorkspacePatch) => void;
  setLastRunId: (lastRunId: string | null) => void;
  recordProbe: (configId: string, summary: ProbeSummary) => void;
}

export const useUiStore = create<UiState>((set, get) => ({
  theme: storedTheme(),
  setTheme: (theme) => {
    localStorage.setItem(THEME_KEY, theme);
    set({ theme });
  },
  resultsTab: "questions",
  setResultsTab: (resultsTab) => set({ resultsTab }),
  columnDraft: {},
  setColumnDraft: (columnDraft) => set({ columnDraft }),
  clearColumnDraft: () => set({ columnDraft: {} }),
  ...storedWorkspace(),
  setWorkspace: (patch) => {
    set(patch);
    persist(get());
  },
  setLastRunId: (lastRunId) => {
    set({ lastRunId });
    persist(get());
  },
  recordProbe: (configId, summary) => {
    set({ probes: { ...get().probes, [configId]: summary } });
    persist(get());
  },
}));

export function applyTheme(theme: ThemeMode) {
  document.documentElement.dataset.theme = theme;
}
