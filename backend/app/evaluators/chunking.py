from __future__ import annotations

from statistics import mean

from app.domain.models import Chunk, EvalContext
from app.domain.text import coverage, jaccard, purity, token_set, tokenize
from app.evaluators.base import Evaluator, gold_text

CARRIER_COVERAGE = 0.15
CERTAIN_COVERAGE = 0.85
SPLIT_EACH = 0.25
SPLIT_UNION = 0.7
MIXED_CERTAIN = 0.4
MIXED_UNCLEAR = 0.6


def _chunk_stats(gold: str, chunks: list[Chunk]) -> list[dict]:
    gold_tokens = token_set(gold)
    rows = []
    for chunk in sorted(chunks, key=lambda item: item.rank):
        covered = gold_tokens & token_set(chunk.text)
        rows.append(
            {
                "chunk": chunk,
                "coverage": coverage(gold, chunk.text),
                "purity": purity(gold, chunk.text),
                "covered": covered,
                "tokens": len(tokenize(chunk.text)),
            }
        )
    return rows


def analyze_chunks(gold: str, chunks: list[Chunk]) -> dict:
    rows = _chunk_stats(gold, chunks)
    carriers = [row for row in rows if row["coverage"] >= CARRIER_COVERAGE]
    certain_whole = any(row["coverage"] >= CERTAIN_COVERAGE for row in rows)
    split_certain = False
    if not certain_whole and len(carriers) >= 2:
        strongest = sorted(carriers, key=lambda row: row["coverage"], reverse=True)[:2]
        union = strongest[0]["covered"] | strongest[1]["covered"]
        gold_size = len(token_set(gold)) or 1
        split_certain = (
            strongest[0]["coverage"] >= SPLIT_EACH
            and strongest[1]["coverage"] >= SPLIT_EACH
            and len(union) / gold_size >= SPLIT_UNION
        )
    if certain_whole:
        split = False
        split_uncertain = False
    elif split_certain:
        split = True
        split_uncertain = False
    elif carriers:
        split = False
        split_uncertain = True
    else:
        split = False
        split_uncertain = False

    mixed = False
    mixed_uncertain = False
    if carriers:
        best_purity = max(carriers, key=lambda row: row["coverage"])["purity"]
        if any(row["purity"] < MIXED_CERTAIN for row in carriers):
            mixed = True
        elif MIXED_CERTAIN <= best_purity <= MIXED_UNCLEAR:
            mixed_uncertain = True

    neighbor_scores = [
        jaccard(rows[index]["chunk"].text, rows[index + 1]["chunk"].text) for index in range(len(rows) - 1)
    ]
    cut_after = []
    carrier_ranks = {row["chunk"].rank for row in carriers}
    for index in range(len(rows) - 1):
        if rows[index]["chunk"].rank in carrier_ranks and rows[index + 1]["chunk"].rank in carrier_ranks:
            cut_after.append(rows[index]["chunk"].rank)
    return {
        "split": split,
        "split_uncertain": split_uncertain,
        "mixed": mixed,
        "mixed_uncertain": mixed_uncertain,
        "neighbor_overlap": mean(neighbor_scores) if neighbor_scores else None,
        "mean_tokens": mean(row["tokens"] for row in rows) if rows else None,
        "cut_after_ranks": cut_after,
        "rows": rows,
        "needs_confirm": split_uncertain or mixed_uncertain,
    }


def neighbor_window(chunks: list[Chunk], rows: list[dict]) -> list[Chunk]:
    if not rows:
        return []
    carriers = [row for row in rows if row["coverage"] >= CARRIER_COVERAGE]
    pool = carriers or rows
    best = max(pool, key=lambda row: row["coverage"])
    ordered = [row["chunk"] for row in rows]
    index = ordered.index(best["chunk"])
    start = max(0, index - 1)
    window = ordered[start : start + 3]
    if len(window) < 2 and len(ordered) >= 2:
        window = ordered[:2]
    return window[:3]


class ChunkMetrics(Evaluator):
    id = "chunk_split"
    metric_ids = ("chunk_split",)
    requires = frozenset({"gold_passage", "chunks"})

    def evaluate(self, ctx: EvalContext):
        gold = gold_text(ctx)
        analysis = analyze_chunks(gold, ctx.primary.chunks)
        split = analysis["split"]
        mixed = analysis["mixed"]
        confirm_called = False
        if analysis["needs_confirm"] and self._judge is not None:
            neighbors = neighbor_window(ctx.primary.chunks, analysis["rows"])
            verdict = self._judge.confirm_chunk_split(gold, neighbors)
            confirm_called = True
            if analysis["split_uncertain"]:
                split = bool(verdict.split_across_chunks)
            if analysis["mixed_uncertain"]:
                mixed = bool(verdict.mixed_topic)
        return [
            self.scored(
                ctx,
                "chunk_split",
                1.0 if split else 0.0,
                {
                    "numerator": 1 if split else 0,
                    "denominator": 1,
                    "mixed_topic": mixed,
                    "neighbor_overlap": analysis["neighbor_overlap"],
                    "mean_chunk_tokens": analysis["mean_tokens"],
                    "cut_after_ranks": analysis["cut_after_ranks"],
                    "confirm_called": confirm_called,
                },
                self._provenance("split_confirm") if confirm_called else None,
            )
        ]

    def aggregate(self, contexts, case_metrics, extras):
        run_id = extras["run_id"]
        mine = [
            row
            for row in case_metrics
            if row.metric_id == "chunk_split" and row.judge_slot == "primary"
        ]
        ran = [row for row in mine if row.status == "ok"]
        if not ran:
            reason = "Check D never ran"
            return [
                self.run_level(run_id, metric_id, None, "skipped", skip_reason=reason)
                for metric_id in ("split_answer_rate", "mixed_topic_rate", "avg_chunk_tokens", "neighbor_overlap")
            ]
        split_count = sum(1 for row in ran if (row.value or 0) >= 1)
        mixed_count = sum(1 for row in ran if (row.details or {}).get("mixed_topic"))
        overlaps = [
            row.details["neighbor_overlap"]
            for row in ran
            if row.details.get("neighbor_overlap") is not None
        ]
        traces = [trace for trace in extras.get("traces", []) if trace.status == "ok" and trace.kind == "primary"]
        lengths: list[int] = []
        for trace in traces:
            for chunk in trace.chunks:
                lengths.append(len(tokenize(chunk.text)))
        histogram = chunk_histogram(lengths)
        results = [
            self.run_level(
                run_id,
                "split_answer_rate",
                split_count / len(ran),
                "ok",
                {"numerator": split_count, "denominator": len(ran)},
            ),
            self.run_level(
                run_id,
                "mixed_topic_rate",
                mixed_count / len(ran),
                "ok",
                {"numerator": mixed_count, "denominator": len(ran)},
            ),
        ]
        if lengths:
            results.append(
                self.run_level(
                    run_id,
                    "avg_chunk_tokens",
                    mean(lengths),
                    "ok",
                    {"numerator": sum(lengths), "denominator": len(lengths), "histogram": histogram},
                )
            )
        else:
            results.append(self.run_level(run_id, "avg_chunk_tokens", None, "skipped", skip_reason="no chunks"))
        if overlaps:
            results.append(
                self.run_level(
                    run_id,
                    "neighbor_overlap",
                    mean(overlaps),
                    "ok",
                    {"numerator": sum(overlaps), "denominator": len(overlaps)},
                )
            )
        else:
            results.append(
                self.run_level(
                    run_id,
                    "neighbor_overlap",
                    None,
                    "skipped",
                    skip_reason="Fewer than two chunks in every case",
                )
            )
        return results


def chunk_histogram(lengths: list[int]) -> list[dict]:
    if not lengths:
        return []
    highest = max(lengths)
    last = (highest // 100) * 100
    counts = {start: 0 for start in range(0, last + 100, 100)}
    for length in lengths:
        counts[(length // 100) * 100] += 1
    return [{"start": start, "end": start + 100, "count": counts[start]} for start in sorted(counts)]
