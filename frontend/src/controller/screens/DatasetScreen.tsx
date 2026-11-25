import { Link } from "react-router-dom";

import { EmptyState, ErrorState, LoadingSkeleton, PageHead } from "../../view/components/Chrome";
import { CasePreview, ColumnMapper, DatasetCheck, DatasetDropzone } from "../../view/components/Dataset";
import { useDatasetUpload } from "../hooks/useDatasetUpload";

export function DatasetScreen() {
  const dataset = useDatasetUpload();
  if (!dataset.projectId && !dataset.projects.length) {
    return <EmptyState title="No file yet" body="Connect a system first so the upload has a project." />;
  }
  if (dataset.loading && !dataset.dataset) {
    return <LoadingSkeleton variant="dataset" />;
  }
  const preview = dataset.cases.length
    ? dataset.cases
    : dataset.dataset?.preview.map((row) => ({
        question: row.question ?? "",
        expected_answer: row.expected_answer ?? null,
        gold_passage: row.gold_passage ?? null,
        conversation_id: row.conversation_id ?? null,
        turn_index: 0,
      })) ?? [];
  return (
    <section>
      <PageHead title="Test dataset" body="Pick a saved project, then upload a file or choose one already stored there. The file is kept in the database, and each row's question column becomes one test question." />
      {dataset.projects.length ? (
        <div className="card" style={{ marginBottom: 18 }}>
          <h2>Project</h2>
          <label>
            Saved project
            <select
              value={dataset.projectId ?? ""}
              onChange={(event) => {
                const project = dataset.projects.find((item) => item.id === event.target.value);
                if (project) {
                  dataset.selectProject(project);
                }
              }}
            >
              <option value="">Choose a project</option>
              {dataset.projects.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name} · {new Date(project.created_at).toLocaleString()}
                </option>
              ))}
            </select>
          </label>
          <p className="hint">Choosing a different project clears the endpoint in use. Click Use on a saved connection for that project before you run.</p>
        </div>
      ) : null}
      {dataset.projectId ? (
      <>
      {dataset.datasets.length ? (
        <div className="card" style={{ marginBottom: 18 }}>
          <h2>Files in this project</h2>
          <p className="hint">Delete removes the file from this project. Runs that used it are removed too.</p>
          <table>
            <thead>
              <tr>
                <th>File</th>
                <th>Questions</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {dataset.datasets.map((item) => (
                <tr key={item.id} className={item.id === dataset.datasetId ? "on" : undefined}>
                  <td>{item.source_filename}</td>
                  <td>
                    {item.case_count}
                    {item.needs_mapping ? " · needs mapping" : ""}
                  </td>
                  <td>
                    <div className="actions" style={{ marginTop: 0 }}>
                      {item.id === dataset.datasetId ? (
                        <span className="tag t-good">In use</span>
                      ) : (
                        <button className="btn s" type="button" onClick={() => dataset.select(item.id)}>
                          Use
                        </button>
                      )}
                      <button
                        className="btn s"
                        type="button"
                        disabled={dataset.deletingId === item.id}
                        onClick={() => dataset.remove(item.id)}
                      >
                        {dataset.deletingId === item.id ? "Deleting…" : "Delete"}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {!dataset.dataset ? <EmptyState title="No file yet" body="Upload a CSV, JSON, or XLSX file." /> : null}
      <DatasetDropzone
        onFile={dataset.upload}
        accept=".csv,.json,.xlsx"
        filename={dataset.dataset?.source_filename}
        count={dataset.dataset?.case_count}
      />
      {dataset.dataset ? (
        <>
          <div className="grid g2" style={{ marginTop: 18 }}>
            <div className="card">
              <h2>Column mapping</h2>
              <ColumnMapper headers={dataset.dataset.headers} mapping={dataset.columnDraft} onChange={dataset.setColumnDraft} />
              <p className="hint" style={{ marginTop: 12 }}>
                Rows sharing a conversation id run in order as one chat, which tests follow-up reasoning.
              </p>
              <div className="actions">
                <button className="btn" type="button" onClick={dataset.saveMapping}>
                  Save mapping
                </button>
              </div>
            </div>
            <DatasetCheck rows={preview} />
          </div>
          <div className="card scroll" style={{ marginTop: 18 }}>
            <h2>Preview</h2>
            <CasePreview rows={preview} />
          </div>
          <div className="actions">
            <Link className="btn p" to="/run">
              Continue to judge setup
            </Link>
          </div>
        </>
      ) : null}
      {dataset.error ? <ErrorState message={dataset.error} onRetry={() => dataset.retry()} /> : null}
      </>
      ) : null}
    </section>
  );
}
