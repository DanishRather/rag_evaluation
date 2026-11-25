import { Link } from "react-router-dom";

import { ErrorState, PageHead } from "../../view/components/Chrome";
import { ActiveConnection, ConnectionList, ProbeResultView, SystemForm } from "../../view/components/Connect";
import { useSystemConnection } from "../hooks/useSystemConnection";

export function ConnectSystemScreen() {
  const connection = useSystemConnection();
  const activeProbe = connection.activeConfigId ? (connection.probes[connection.activeConfigId] ?? null) : null;
  const ready = Boolean(connection.active && activeProbe?.ok);
  return (
    <section>
      <PageHead
        title="Connect your RAG system"
        body="Save how to call your endpoint, then test it with one question. Runs send every dataset question to the connection in use."
      />
      <ActiveConnection connection={connection.active} probe={activeProbe} />
      <SystemForm
        value={connection.draft}
        onChange={connection.setDraft}
        onSubmit={connection.save}
        disabled={connection.saving}
        error={connection.error}
      />
      {connection.error ? <ErrorState message={connection.error} onRetry={() => connection.retry()} /> : null}
      <ProbeResultView probe={connection.probe} query={connection.draft.testQuery} />
      {ready ? (
        <div className="actions">
          <Link className="btn p" to="/dataset">
            Upload a test file
          </Link>
          <Link className="btn" to="/run">
            Go to judge and run
          </Link>
        </div>
      ) : null}
      {connection.testError ? <ErrorState message={connection.testError} /> : null}
      <ConnectionList
        connections={connection.connections}
        activeConfigId={connection.activeConfigId}
        probes={connection.probes}
        testingId={connection.testingId}
        onUse={connection.use}
        onTest={connection.test}
        onDelete={connection.remove}
        onClearBroken={connection.clearBroken}
        clearing={connection.clearing}
      />
    </section>
  );
}
