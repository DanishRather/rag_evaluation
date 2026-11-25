import { Link, useParams } from "react-router-dom";

import { EmptyState, ErrorState, LoadingSkeleton, PageHead } from "../../view/components/Chrome";
import { CalibrationBanner, CompareBlock, FindingList, ScoreSummary, SetupTable, SkippedPanel } from "../../view/components/Report";
import { useCompareRuns, useSetupReport } from "../hooks/useSetupReport";

export function SetupReportScreen() {
  const { runId = "" } = useParams();
  const report = useSetupReport(runId);
  const compare = useCompareRuns(runId);
  if (report.loading) {
    return <LoadingSkeleton variant="report" />;
  }
  if (report.run && report.run.status !== "succeeded" && !report.report) {
    return <EmptyState title="Report not ready" body="The report appears when the run succeeds." />;
  }
  if (report.error) {
    return <ErrorState message={report.error} onRetry={() => report.retry()} />;
  }
  if (!report.report) {
    return <EmptyState title="Report not ready" body="The report appears when the run succeeds." />;
  }
  const model = report.report;
  return (
    <section>
      <PageHead title="Setup report" body="What to change in the RAG system, based on this run." />
      <p>{model.summary_text}</p>
      <div className="actions">
        <a className="btn p" href={report.htmlPath}>
          Download HTML
        </a>
        <a className="btn" href={report.pdfPath}>
          Download PDF
        </a>
        <Link className="btn" to={`/runs/${runId}/results`}>
          Back to results
        </Link>
      </div>
      <div className="card scroll" style={{ marginTop: 18 }}>
        <ScoreSummary metrics={model.score_summary} />
      </div>
      <div className="card" style={{ marginTop: 18 }}>
        <h2>What could not be measured</h2>
        <SkippedPanel groups={model.skipped} />
      </div>
      <div className="card" style={{ marginTop: 18 }}>
        <h2>Findings</h2>
        <FindingList findings={model.findings} />
      </div>
      <div className="card scroll" style={{ marginTop: 18 }}>
        <h2>Suggested settings</h2>
        <SetupTable rows={model.setup_table} />
        <div className="actions">
          <Link className="btn p" to="/run">
            Re-run from judge setup
          </Link>
        </div>
      </div>
      <div className="card" style={{ marginTop: 18 }}>
        <h2>Compare with another run</h2>
        <label>
          Other run id
          <input value={compare.otherId} onChange={(event) => compare.setOtherId(event.target.value)} />
        </label>
        {compare.error ? <ErrorState message={compare.error} /> : null}
        <CompareBlock compare={compare.compare} />
      </div>
      <div className="card" style={{ marginTop: 18 }}>
        <h2>Calibration</h2>
        <CalibrationBanner agreement={model.calibration} />
      </div>
    </section>
  );
}
