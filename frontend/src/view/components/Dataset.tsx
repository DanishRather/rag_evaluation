import type { TestCase } from "../../model/types";

const FIELDS = ["question", "expected_answer", "gold_passage", "conversation_id"] as const;

export function DatasetDropzone({
  onFile,
  accept,
  filename,
  count,
}: {
  onFile: (file: File) => void;
  accept: string;
  filename?: string;
  count?: number;
}) {
  return (
    <label className="drop">
      <strong>Drop a CSV, JSON or XLSX file here</strong>
      <br />
      or browse files
      {filename ? (
        <>
          {" "}
          · loaded: <b>{filename}</b>
          {typeof count === "number" ? ` (${count} rows)` : ""}
        </>
      ) : null}
      <input
        type="file"
        accept={accept}
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) {
            onFile(file);
          }
        }}
      />
    </label>
  );
}

export function DatasetCheck({
  rows,
}: {
  rows: { expected_answer: string | null; gold_passage: string | null; conversation_id: string | null; turn_index: number }[];
}) {
  const withSource = rows.filter((row) => row.gold_passage).length;
  const withoutSource = rows.length - withSource;
  const followups = rows.filter((row) => row.turn_index > 0).length;
  const chats = new Set(rows.map((row) => row.conversation_id).filter(Boolean)).size;
  return (
    <div className="card">
      <h2>Dataset check</h2>
      <p style={{ marginTop: 8 }}>
        <span className="tag t-good">{rows.length} questions</span>{" "}
        <span className="tag t-good">{withSource} with source passage</span>{" "}
        {withoutSource ? <span className="tag t-warn">{withoutSource} without source</span> : null}
      </p>
      <p style={{ marginTop: 10 }}>
        <span className="tag t-n">{chats} chats</span> <span className="tag t-n">{followups} follow-up turns</span>
      </p>
      <p className="hint" style={{ marginTop: 12 }}>
        Rows without a source passage are scored on answer quality only.
      </p>
    </div>
  );
}

export function ColumnMapper({
  headers,
  mapping,
  onChange,
}: {
  headers: string[];
  mapping: Record<string, string>;
  onChange: (mapping: Record<string, string>) => void;
}) {
  return (
    <fieldset>
      <legend>Column map</legend>
      {FIELDS.map((field) => (
        <label key={field}>
          {field}
          <select
            value={mapping[field] ?? ""}
            onChange={(event) => onChange({ ...mapping, [field]: event.target.value })}
          >
            <option value="">Not mapped</option>
            {headers.map((header) => (
              <option key={header} value={header}>
                {header}
              </option>
            ))}
          </select>
        </label>
      ))}
    </fieldset>
  );
}

export function CasePreview({ rows }: { rows: Pick<TestCase, "question" | "expected_answer" | "gold_passage" | "turn_index">[] }) {
  if (!rows.length) {
    return <p>No cases yet.</p>;
  }
  return (
    <table>
      <caption>Case preview</caption>
      <thead>
        <tr>
          <th>Turn</th>
          <th>Question</th>
          <th>Expected</th>
          <th>Gold passage</th>
        </tr>
      </thead>
      <tbody>
        {rows.slice(0, 8).map((row, index) => (
          <tr key={`${row.turn_index}-${index}`}>
            <td>{row.turn_index}</td>
            <td>{row.question}</td>
            <td>{row.expected_answer ?? ""}</td>
            <td>{row.gold_passage ?? ""}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
