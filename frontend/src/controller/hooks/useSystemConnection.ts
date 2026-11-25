import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";

import { emptySystemDraft } from "../../view/components/Connect";
import { useUiStore } from "../../model/stores/ui";
import type { Connection, SystemDraft } from "../../model/types";
import { draftFromConnection, queryKeys, sendsEachQuestion, summarizeProbe } from "../../services";
import { useServices } from "../services";

export function useSystemConnection() {
  const services = useServices();
  const projectId = useUiStore((state) => state.projectId);
  const datasetId = useUiStore((state) => state.datasetId);
  const configId = useUiStore((state) => state.configId);
  const probes = useUiStore((state) => state.probes);
  const setWorkspace = useUiStore((state) => state.setWorkspace);
  const recordProbe = useUiStore((state) => state.recordProbe);
  const [draft, setDraft] = useState<SystemDraft>(emptySystemDraft);
  const [localError, setLocalError] = useState("");
  const connections = useQuery({
    queryKey: queryKeys.connections,
    queryFn: () => services.system.connections(),
  });
  const unique = useMemo(() => uniqueConnections(connections.data ?? [], configId), [connections.data, configId]);
  const active = unique.find((item) => item.config.id === configId) ?? null;
  const prefilled = useRef(false);
  useEffect(() => {
    if (prefilled.current || !active) {
      return;
    }
    prefilled.current = true;
    setDraft(usableDraft(active));
  }, [active]);

  function select(connection: Connection) {
    setWorkspace({
      projectId: connection.project_id,
      systemId: connection.system_id,
      configId: connection.config.id,
      projectName: connection.project_name,
      systemName: connection.system_name,
      endpointUrl: String(connection.config.adapter_settings.url ?? ""),
      datasetId: connection.project_id === projectId ? datasetId : null,
    });
  }

  const save = useMutation({
    mutationFn: (next: SystemDraft) => services.system.connect(next, projectId),
    onSuccess: (result) => {
      setWorkspace({
        projectId: result.project.id,
        systemId: result.system.id,
        configId: result.config.id,
        projectName: result.project.name,
        systemName: result.system.name,
        endpointUrl: String(result.config.adapter_settings.url ?? ""),
        datasetId: result.project.id === projectId ? datasetId : null,
      });
      recordProbe(result.config.id, summarizeProbe(result.probe));
    },
  });
  const test = useMutation({
    mutationFn: ({ id, question }: { id: string; question: string }) => services.system.probe(id, question),
    onSuccess: (probe, { id }) => recordProbe(id, summarizeProbe(probe)),
    onError: (error, { id }) =>
      recordProbe(id, { ok: false, message: error instanceof Error ? error.message : "Test failed", at: new Date().toISOString() }),
  });

  function readyQuery(): string | null {
    const query = draft.testQuery.trim();
    if (!query) {
      setLocalError("Enter the query to test.");
      return null;
    }
    setLocalError("");
    return query;
  }

  function submit() {
    if (!draft.projectName.trim() || !draft.systemName.trim() || !draft.url.trim()) {
      setLocalError("Project name, system name, and endpoint URL are required.");
      return;
    }
    if (!readyQuery()) {
      return;
    }
    const next = sendsEachQuestion(draft.requestTemplate) ? draft : { ...draft, requestTemplate: templateFor(draft.encoding) };
    setDraft(next);
    save.mutate(next);
  }

  const remove = useMutation({
    mutationFn: (systemId: string) => services.system.delete(systemId),
    onSuccess: (_result, systemId) => {
      if (systemId === useUiStore.getState().systemId) {
        setWorkspace({ systemId: null, configId: null, systemName: "", endpointUrl: "" });
      }
    },
  });
  const clearBroken = useMutation({
    mutationFn: () => services.system.deleteBroken(),
    onSuccess: () => {
      const current = (connections.data ?? []).find((item) => item.system_id === useUiStore.getState().systemId);
      const template = String(current?.config.adapter_settings.request_template ?? "");
      if (current && template && !sendsEachQuestion(template)) {
        setWorkspace({ systemId: null, configId: null, systemName: "", endpointUrl: "" });
      }
    },
  });

  const requestError = save.error instanceof Error ? save.error.message : "";
  const testError = test.error instanceof Error ? test.error.message : "";
  const removeError = remove.error instanceof Error ? remove.error.message : "";
  return {
    draft,
    setDraft,
    error: localError || requestError || removeError,
    probe: save.data?.probe ?? null,
    save: submit,
    saving: save.isPending,
    retry: submit,
    connections: unique,
    connectionsLoading: connections.isLoading,
    active,
    activeConfigId: configId,
    probes,
    use: (connection: Connection) => {
      select(connection);
      setDraft(usableDraft(connection));
    },
    remove: (systemId: string) => remove.mutate(systemId),
    clearBroken: () => clearBroken.mutate(),
    clearing: clearBroken.isPending,
    test: (id: string) => {
      const question = readyQuery();
      if (question) {
        test.mutate({ id, question });
      }
    },
    testingId: test.isPending ? (test.variables?.id ?? null) : null,
    testError,
  };
}

function usableDraft(connection: Connection): SystemDraft {
  const draft = draftFromConnection(connection);
  if (sendsEachQuestion(draft.requestTemplate)) {
    return draft;
  }
  return {
    ...draft,
    encoding: "form",
    requestTemplate: templateFor("form"),
    answerPath: draft.answerPath === "$.answer" ? "$.content" : draft.answerPath,
  };
}

function templateFor(encoding: SystemDraft["encoding"]) {
  return encoding === "form" ? "message={{ question }}" : '{"question": {{ question | tojson }}}';
}

function uniqueConnections(rows: Connection[], activeConfigId: string | null): Connection[] {
  const chosen = new Map<string, Connection>();
  for (const row of rows) {
    const settings = row.config.adapter_settings;
    const key = JSON.stringify([
      row.project_name,
      row.system_name,
      settings.url,
      settings.request_template,
      settings.encoding,
      (settings.response_map as Record<string, unknown> | undefined)?.answer,
    ]);
    if (!chosen.has(key) || row.config.id === activeConfigId) {
      chosen.set(key, row);
    }
  }
  return [...chosen.values()];
}
