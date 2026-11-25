import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import { useUiStore } from "../../model/stores/ui";
import type { ColumnMap, Project } from "../../model/types";
import { queryKeys } from "../../services";
import { useServices } from "../services";

export function useDatasetUpload() {
  const services = useServices();
  const projectId = useUiStore((state) => state.projectId);
  const datasetId = useUiStore((state) => state.datasetId);
  const columnDraft = useUiStore((state) => state.columnDraft);
  const setColumnDraft = useUiStore((state) => state.setColumnDraft);
  const clearColumnDraft = useUiStore((state) => state.clearColumnDraft);
  const setWorkspace = useUiStore((state) => state.setWorkspace);
  const projects = useQuery({
    queryKey: queryKeys.projects,
    queryFn: () => services.system.listProjects(),
  });
  const datasets = useQuery({
    queryKey: queryKeys.datasets(projectId ?? "none"),
    queryFn: () => services.dataset.list(projectId as string),
    enabled: Boolean(projectId),
  });
  const dataset = useQuery({
    queryKey: queryKeys.dataset(datasetId ?? "none"),
    queryFn: () => services.dataset.get(datasetId as string),
    enabled: Boolean(datasetId),
  });
  const drafted = useRef<string | null>(null);
  useEffect(() => {
    if (!dataset.data || drafted.current === dataset.data.id) {
      return;
    }
    drafted.current = dataset.data.id;
    setColumnDraft({ ...dataset.data.column_map });
  }, [dataset.data, setColumnDraft]);
  const cases = useQuery({
    queryKey: queryKeys.cases(datasetId ?? "none"),
    queryFn: () => services.dataset.cases(datasetId as string),
    enabled: Boolean(datasetId) && dataset.data?.needs_mapping === false,
  });
  const upload = useMutation({
    mutationFn: (file: File) => services.dataset.upload(projectId as string, file),
    onSuccess: (next) => {
      drafted.current = next.id;
      setColumnDraft({ ...next.column_map });
      setWorkspace({ datasetId: next.id, projectId: next.project_id });
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) => services.dataset.delete(id, projectId as string),
    onSuccess: (_result, id) => {
      if (datasetId === id) {
        setWorkspace({ datasetId: null });
      }
    },
  });
  const save = useMutation({
    mutationFn: () => {
      const mapping: ColumnMap = {
        question: columnDraft.question,
        expected_answer: columnDraft.expected_answer || null,
        gold_passage: columnDraft.gold_passage || null,
        conversation_id: columnDraft.conversation_id || null,
      };
      return services.dataset.saveMapping(datasetId as string, mapping);
    },
    onSuccess: () => clearColumnDraft(),
  });
  const error = upload.error ?? save.error ?? remove.error ?? dataset.error;
  const current = datasetId ? (dataset.data ?? upload.data ?? null) : null;
  function selectProject(project: Project) {
    if (project.id === projectId) {
      return;
    }
    setWorkspace({
      projectId: project.id,
      projectName: project.name,
      datasetId: null,
      systemId: null,
      configId: null,
      systemName: "",
      endpointUrl: "",
    });
  }

  return {
    projectId,
    projects: projects.data ?? [],
    selectProject,
    datasets: datasets.data ?? [],
    datasetId,
    select: (id: string) => setWorkspace({ datasetId: id || null }),
    dataset: current,
    cases: cases.data ?? [],
    columnDraft,
    setColumnDraft,
    upload: (file: File) => upload.mutate(file),
    remove: (id: string) => remove.mutate(id),
    deletingId: remove.isPending ? (remove.variables ?? null) : null,
    saveMapping: () => save.mutate(),
    loading: dataset.isLoading || upload.isPending,
    error: error instanceof Error ? error.message : "",
    retry: () => dataset.refetch(),
  };
}
