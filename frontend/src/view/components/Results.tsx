import type { Chunk, MetricResult, MetricSummaryRow, Trace } from "../../model/types";

import { formatCount, formatDuration, formatValue, tokens } from "../format";

export interface QuestionRow {
  question: string;
  answer: string;
  correctness: MetricResult | undefined;
  faithfulness: MetricResult | undefined;
  status: string;
  testCaseId: string;
}

const SCORE_CARDS = [
  { id: "correctness", label: "Answer quality" },
  { id: "faithfulness", label: "Faithfulness" },
  { id: "hit", label: "Retrieval hit rate" },
  { id: "split_answer_rate", label: "Split answers", invert: true },
  { id: "history_failure_rate", label: "History failures", invert: true },
] as const;

export function ScoreCards({ summary }: { summary: Record<string, MetricSummaryRow | undefined> }) {
  return (
    <div className="grid g5">
      {SCORE_CARDS.map((card) => {
        const row = summary[card.id];
        const value = row?.status === "ok" ? row.value : null;
        return (
          <div className="card score" key={card.id}>
            <div className="n">{row && row.status === "ok" ? formatValue(row.value) : "Not scored"}</div>
            <div className="l">{card.label}</div>
            {value === null ? (
              <p className="hint">{plainReason(typeof row?.details?.skip_reason === "string" ? row.details.skip_reason : undefined)}</p>
            ) : (
              <div className={`bar ${barTone(value, "invert" in card)}`} aria-hidden="true">
                <b style={{ width: `${barWidth(value)}%` }} />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

export function MetricBars({
  rows,
  summary,
}: {
  rows: { id: string; label: string; invert?: boolean }[];
  summary: Record<string, MetricSummaryRow | undefined>;
}) {
  return (
    <div className="card">
      <h3>Stored metrics</h3>
      {rows.map((item) => {
        const row = summary[item.id];
        const value = row?.status === "ok" ? row.value : null;
        return (
          <div key={item.id}>
            <p>
              {item.label} <b style={{ float: "right" }}>{row && row.status === "ok" ? formatValue(row.value) : "—"}</b>
            </p>
            <div className={`bar ${barTone(value, Boolean(item.invert))}`}>
              <b style={{ width: `${barWidth(value)}%` }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function barWidth(value: number | null) {
  if (value === null) {
    return 0;
  }
  return Math.max(0, Math.min(100, Math.abs(value) <= 1 ? value * 100 : 100));
}

function barTone(value: number | null, invert: boolean) {
  if (value === null || Math.abs(value) > 1) {
    return "";
  }
  const score = invert ? 1 - value : value;
  if (score >= 0.75) {
    return "g";
  }
  if (score >= 0.6) {
    return "w";
  }
  return "r";
}

export function QuestionTable({ rows }: { rows: QuestionRow[] }) {
  return (
    <table>
      <caption>Questions</caption>
      <thead>
        <tr>
          <th>Question</th>
          <th>Answer</th>
          <th>Result</th>
          <th>Faithfulness</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.testCaseId}>
            <td>{row.question}</td>
            <td>{row.answer}</td>
            <td>
              <Verdict metric={row.correctness} kind="correctness" />
            </td>
            <td>
              <Verdict metric={row.faithfulness} kind="faithfulness" />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Verdict({ metric, kind }: { metric: MetricResult | undefined; kind: "correctness" | "faithfulness" }) {
  if (!metric || metric.status !== "ok" || metric.value === null) {
    return (
      <div>
        <span className="tag t-n">Not scored</span>
        <div className="hint">{plainReason(metric?.skip_reason)}</div>
      </div>
    );
  }
  const passed = metric.value >= 0.8;
  const label = kind === "correctness" ? (passed ? "Correct" : "Incorrect") : passed ? "Grounded" : "Not grounded";
  return (
    <div>
      <span className={passed ? "tag t-good" : "tag t-bad"}>{label}</span>
      <div className="hint">{cell(metric)}</div>
    </div>
  );
}

function plainReason(reason: string | null | undefined) {
  const text = REASONS[reason ?? ""] ?? reason;
  return text || "This check did not produce a score.";
}

const REASONS: Record<string, string> = {
  "judge output invalid": "The judge did not return a score.",
  "no chunks": "No passages came back with the answer.",
  "no gold passage": "This question has no source passage in the dataset.",
  "no expected answer": "This question has no expected answer.",
  "not a follow-up": "This question is not a follow-up.",
  "no standalone trace": "No standalone rewrite was stored.",
  "judge returned no facts": "The judge found no facts to check.",
  "judge returned no claims": "The judge found no claims to check.",
};

export function passagesFromAnswer(answer: string | null | undefined, existing: Chunk[]): Chunk[] {
  if (existing.length) {
    return existing;
  }
  if (!answer) {
    return [];
  }
  const section = answer.split(/##\s+References/i)[1] ?? "";
  return section
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.startsWith("- "))
    .map((line, index) => passageFromReference(line, index + 1))
    .filter((chunk): chunk is Chunk => chunk !== null);
}

function passageFromReference(line: string, rank: number): Chunk | null {
  const matched = line.match(/^-\s+\[([^\]]+)\]\([^)]*\)\s+[—-]\s+(.+)$/);
  const source = matched?.[1] ?? null;
  const body = (matched?.[2] ?? line.replace(/^-+\s+/, "")).replace(/<!--[\s\S]*$/, "").trim();
  if (!body) {
    return null;
  }
  const cites = [...body.matchAll(/\[(C\d+)\]/g)].map((item) => item[1]);
  return {
    chunk_key: cites[0] ?? source ?? `ref-${rank}`,
    rank,
    text: body,
    score: null,
    source,
    page: null,
    token_length: tokens(body).length,
  };
}

export function RunFacts({
  summary,
  answers,
  cited,
}: {
  summary: Record<string, MetricSummaryRow | undefined>;
  answers: number;
  cited: number;
}) {
  const failed = summary.error_rate;
  const returned =
    failed?.status === "ok" && failed.denominator
      ? `${failed.denominator - (failed.numerator ?? 0)}/${failed.denominator}`
      : String(answers);
  const facts = [
    { label: "Answers returned", value: returned },
    { label: "Median latency", value: durationOf(summary.latency_p50) },
    { label: "Prompt tokens", value: countOf(summary.prompt_tokens) },
    { label: "Completion tokens", value: countOf(summary.completion_tokens) },
    { label: "Cited a source", value: answers ? `${cited}/${answers}` : "—" },
  ];
  return (
    <div className="grid g5" style={{ marginTop: 18 }}>
      {facts.map((fact) => (
        <div className="card score" key={fact.label}>
          <div className="n">{fact.value}</div>
          <div className="l">{fact.label}</div>
        </div>
      ))}
    </div>
  );
}

function durationOf(row: MetricSummaryRow | undefined) {
  return row?.status === "ok" ? formatDuration(row.value) : "—";
}

function countOf(row: MetricSummaryRow | undefined) {
  return row?.status === "ok" ? formatCount(row.value) : "—";
}

export function RetrievalTable({
  rows,
}: {
  rows: { question: string; passages: Chunk[]; latencyMs: number | null; promptTokens: number | null; completionTokens: number | null }[];
}) {
  return (
    <table>
      <caption>What the endpoint returned</caption>
      <thead>
        <tr>
          <th>Question</th>
          <th>Passages cited</th>
          <th>Latency</th>
          <th>Tokens</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.question}>
            <td>{row.question}</td>
            <td>{row.passages.length ? row.passages.map((chunk) => chunk.text).join(" ") : "No source cited"}</td>
            <td>{formatDuration(row.latencyMs)}</td>
            <td>
              {formatCount(row.promptTokens)} in
              <br />
              {formatCount(row.completionTokens)} out
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function ChunkCard({ chunk }: { chunk: Chunk }) {
  return (
    <article className="card">
      <h3>
        Rank {chunk.rank} · {chunk.chunk_key}
      </h3>
      <p>{chunk.text}</p>
      <p className="muted">
        Score {chunk.score ?? "—"} · {chunk.source ?? "no source"} · page {chunk.page ?? "—"} · tokens{" "}
        {chunk.token_length ?? "—"}
      </p>
    </article>
  );
}

export function ChunkList({ chunks }: { chunks: Chunk[] }) {
  const ordered = [...chunks].sort((left, right) => left.rank - right.rank);
  return (
    <div>
      {ordered.map((chunk) => (
        <ChunkCard key={`${chunk.rank}-${chunk.chunk_key}`} chunk={chunk} />
      ))}
    </div>
  );
}

export function GoldHighlight({ text, gold }: { text: string; gold: string }) {
  const goldTokens = new Set(tokens(gold));
  const parts = text.split(/(\s+)/);
  return (
    <p>
      {parts.map((part, index) => {
        const key = tokens(part)[0];
        if (key && goldTokens.has(key)) {
          return (
            <mark key={index}>
              {part}
            </mark>
          );
        }
        return <span key={index}>{part}</span>;
      })}
    </p>
  );
}

export function SplitStrip({ chunks, cutAfterRanks }: { chunks: Chunk[]; cutAfterRanks: number[] }) {
  const ordered = [...chunks].sort((left, right) => left.rank - right.rank);
  return (
    <div className="chunks" aria-label="Chunk boundaries">
      {ordered.map((chunk) => {
        const cut = cutAfterRanks.includes(chunk.rank);
        return (
          <span key={chunk.rank} className={cut ? "cut" : undefined}>
            {chunk.chunk_key || `Rank ${chunk.rank}`}
            {cut ? " cut" : ""}
          </span>
        );
      })}
    </div>
  );
}

export function OverlapHighlight({ left, right }: { left: string; right: string }) {
  const shared = new Set(tokens(left).filter((token) => new Set(tokens(right)).has(token)));
  return (
    <p>
      Shared tokens:{" "}
      {[...shared].map((token) => (
        <mark key={token}>{token} </mark>
      ))}
    </p>
  );
}

export function ChunkHistogram({ buckets }: { buckets: { start: number; end: number; count: number }[] }) {
  const max = Math.max(1, ...buckets.map((bucket) => bucket.count));
  return (
    <div>
      <div className="bars" aria-hidden="true">
        {buckets.map((bucket) => (
          <div key={bucket.start} style={{ height: `${(bucket.count / max) * 100}%` }} title={`${bucket.count}`} />
        ))}
      </div>
      <table>
        <caption>Chunk size buckets</caption>
        <thead>
          <tr>
            <th>Start</th>
            <th>End</th>
            <th>Count</th>
          </tr>
        </thead>
        <tbody>
          {buckets.map((bucket) => (
            <tr key={bucket.start}>
              <td>{bucket.start}</td>
              <td>{bucket.end}</td>
              <td>{bucket.count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ConversationTimeline({ turns }: { turns: { turn: number; question: string; answer: string }[] }) {
  return (
    <ol>
      {turns.map((turn) => (
        <li key={turn.turn}>
          <strong>Turn {turn.turn}.</strong> {turn.question}
          <p>{turn.answer}</p>
        </li>
      ))}
    </ol>
  );
}

export function RewriteCompare({
  original,
  systemRewrite,
  standalone,
}: {
  original: string;
  systemRewrite: string | null;
  standalone: string | null;
}) {
  return (
    <dl>
      <dt>Original</dt>
      <dd>{original}</dd>
      <dt>System rewrite</dt>
      <dd>{systemRewrite || "Not returned"}</dd>
      <dt>Standalone question</dt>
      <dd>{standalone || "Not stored"}</dd>
    </dl>
  );
}

export function RetrievalSideBySide({ primaryChunks, standaloneChunks }: { primaryChunks: Chunk[]; standaloneChunks: Chunk[] }) {
  return (
    <div className="split">
      <section>
        <h3>Original retrieval</h3>
        <ChunkList chunks={primaryChunks} />
      </section>
      <section>
        <h3>Standalone retrieval</h3>
        <ChunkList chunks={standaloneChunks} />
      </section>
    </div>
  );
}

export function HistoryBadge({ standaloneHit, primaryHit }: { standaloneHit: boolean; primaryHit: boolean }) {
  if (!(standaloneHit && !primaryHit)) {
    return null;
  }
  return <p className="badge">History miss: standalone hit, original miss</p>;
}

const MODEL_ROWS = [
  ["latency_p50", "Median latency"],
  ["latency_p95", "95th percentile latency"],
  ["prompt_tokens", "Prompt tokens"],
  ["completion_tokens", "Completion tokens"],
  ["error_rate", "Answers that failed"],
  ["judge_prompt_tokens", "Judge prompt tokens"],
  ["judge_completion_tokens", "Judge completion tokens"],
  ["judge_cost", "Judge cost"],
  ["target_cost", "Target cost"],
] as const;

export function ModelCostTable({ summary }: { summary: Record<string, MetricSummaryRow | undefined> }) {
  return (
    <table>
      <caption>Model and cost</caption>
      <thead>
        <tr>
          <th>Measure</th>
          <th>Score</th>
        </tr>
      </thead>
      <tbody>
        {MODEL_ROWS.map(([id, label]) => {
          const row = summary[id];
          return (
            <tr key={id}>
              <td>{label}</td>
              <td>{modelScore(id, row)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function modelScore(id: string, row: MetricSummaryRow | undefined) {
  if (!row || row.status !== "ok" || row.value === null) {
    return "Not recorded";
  }
  if (id.startsWith("latency_")) {
    return formatDuration(row.value);
  }
  if (id.endsWith("_tokens")) {
    return formatCount(row.value);
  }
  if (id === "error_rate" && row.numerator !== null && row.denominator !== null) {
    return `${formatValue(row.value)} (${row.numerator}/${row.denominator})`;
  }
  return formatValue(row.value);
}

export function citedPassages(trace: Pick<Trace, "answer" | "chunks">) {
  return passagesFromAnswer(trace.answer, trace.chunks);
}

function cell(row: MetricResult | undefined) {
  if (!row) {
    return "—";
  }
  if (row.status !== "ok") {
    return row.skip_reason || row.status;
  }
  const numerator = row.details.numerator;
  const denominator = row.details.denominator;
  return `${formatValue(row.value)} (${String(numerator)}/${String(denominator)})`;
}
