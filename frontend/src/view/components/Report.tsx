import type { CalibrationAgreement, CompareResult, Finding, SetupRow } from "../../model/types";

import { formatCount, formatDuration, formatValue } from "../format";

const ICONS: Record<string, string> = {
  critical: "▲",
  high: "!",
  medium: "•",
  low: "·",
  info: "i",
};

const LABELS: Record<string, string> = {
  correctness: "Correctness",
  faithfulness: "Faithfulness",
  hit: "Hit rate",
  mrr: "MRR",
  precision_at_k: "Precision",
  recall_at_k: "Recall",
  chunk_split: "Split answers",
  split_answer_rate: "Split answer rate",
  mixed_topic_rate: "Mixed topic rate",
  avg_chunk_tokens: "Average passage length",
  neighbor_overlap: "Neighbor overlap",
  history_failure: "History failure",
  history_failure_rate: "History failure rate",
  error_rate: "Error rate",
  latency_p50: "Median latency",
  latency_p95: "Slow answers",
  prompt_tokens: "Prompt tokens",
  completion_tokens: "Completion tokens",
  judge_variance: "Judge variance",
  judge_disagreement: "Judge disagreement",
};

const REASONS: Record<string, string> = {
  "judge output invalid": "The judge did not return a score.",
  "no chunks": "No passages came back with the answer.",
  "no gold passage": "This file has no source passage.",
  "no expected answer": "This question has no expected answer.",
  "not a follow-up": "This file has no follow-up questions.",
  "no standalone trace": "No standalone rewrite was stored.",
  "No follow-up was scored": "This file has no follow-up questions.",
  "No secondary judge": "Only one judge was configured.",
  "repeats == 1": "Each question was asked once.",
  "Check D never ran": "Passage overlap was not scored.",
};

export function ScoreSummary({
  metrics,
}: {
  metrics: {
    id: string;
    value: number | null;
    numerator: number | null;
    denominator: number | null;
    status: string;
    skip_reason?: string | null;
  }[];
}) {
  const rows = [...metrics].sort((left, right) => Number(right.status === "ok") - Number(left.status === "ok"));
  return (
    <table>
      <caption>Score summary</caption>
      <thead>
        <tr>
          <th>Metric</th>
          <th>Value</th>
          <th>Numerator</th>
          <th>Denominator</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.id}>
            <td>{LABELS[row.id] ?? row.id}</td>
            <td>{row.status === "ok" ? metricValue(row.id, row.value) : plainReason(row.skip_reason)}</td>
            <td>{row.numerator ?? "—"}</td>
            <td>{row.denominator ?? "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function metricValue(id: string, value: number | null) {
  if (id.startsWith("latency_")) {
    return formatDuration(value);
  }
  if (id.endsWith("_tokens")) {
    return formatCount(value);
  }
  return formatValue(value);
}

function plainReason(reason: string | null | undefined) {
  if (!reason) {
    return "Not scored";
  }
  return REASONS[reason] ?? reason;
}

export function SkippedPanel({ groups }: { groups: { reason: string; count: number }[] }) {
  if (!groups.length) {
    return <p>Everything requested could be measured.</p>;
  }
  return (
    <ul>
      {groups.map((group) => (
        <li key={group.reason}>
          {group.reason}: {group.count}
        </li>
      ))}
    </ul>
  );
}

export function FindingList({ findings }: { findings: Finding[] }) {
  return (
    <ul className="findings">
      {findings.map((finding) => (
        <li key={finding.id} className={findingTone(finding.severity)}>
          <b>
            <span aria-hidden="true">{ICONS[finding.severity] ?? "•"} </span>
            {finding.cause}
          </b>
          <p>
            {finding.severity} · {finding.count} · {finding.prose || "No writer note."}
          </p>
          <p>Examples: {finding.example_question_ids.join(", ") || "none"}</p>
        </li>
      ))}
    </ul>
  );
}

function findingTone(severity: string) {
  if (severity === "critical" || severity === "high") {
    return "find bad";
  }
  if (severity === "low" || severity === "info") {
    return "find good";
  }
  return "find";
}

export function SetupTable({ rows }: { rows: SetupRow[] }) {
  return (
    <table>
      <caption>Setup</caption>
      <thead>
        <tr>
          <th>Setting</th>
          <th>Current</th>
          <th>Try</th>
          <th>Why</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.id}>
            <td>{row.setting}</td>
            <td>{row.current}</td>
            <td>{row.try}</td>
            <td>{row.why}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function CompareBlock({ compare }: { compare: CompareResult | null }) {
  if (!compare) {
    return <p>Select a second run to compare.</p>;
  }
  return (
    <div>
      <table>
        <caption>Metric deltas</caption>
        <thead>
          <tr>
            <th>Metric</th>
            <th>A</th>
            <th>B</th>
            <th>Delta</th>
          </tr>
        </thead>
        <tbody>
          {compare.metrics.map((row) => (
            <tr key={row.metric_id}>
              <td>{row.metric_id}</td>
              <td>{formatValue(row.a)}</td>
              <td>{formatValue(row.b)}</td>
              <td>{formatValue(row.delta)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p>Resolved: {compare.resolved.map((row) => row.rule_id).join(", ") || "none"}</p>
      <p>Added: {compare.added.map((row) => row.rule_id).join(", ") || "none"}</p>
      <p>Still present: {compare.still_present.map((row) => row.rule_id).join(", ") || "none"}</p>
    </div>
  );
}

export function CalibrationBanner({ agreement }: { agreement: CalibrationAgreement | null }) {
  if (!agreement) {
    return <p>Calibration appears after the run has scores.</p>;
  }
  return (
    <p role="status">
      {agreement.message}
      {agreement.trusted && agreement.kappa !== null ? ` Kappa ${agreement.kappa.toFixed(2)}.` : ""}
    </p>
  );
}
