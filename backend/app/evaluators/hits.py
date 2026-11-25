"""Shared hit decision. Jaccard bands, with the usefulness agent only in the gray band."""

from __future__ import annotations

from app.domain.models import Chunk, EvalContext
from app.domain.text import jaccard
from app.evaluators.base import gold_text

HIT_AT = 0.5
MISS_BELOW = 0.2


def decide_hits(
    ctx: EvalContext,
    chunks: list[Chunk],
    *,
    cache_prefix: str = "primary",
    question: str | None = None,
) -> list[bool]:
    """Return usefulness for the first k chunks by rank. Missing ranks are not useful."""
    k = max(int(ctx.top_k), 1)
    ranked = sorted(chunks, key=lambda chunk: chunk.rank)[:k]
    flags: list[bool] = []
    gold = gold_text(ctx)
    asked = ctx.primary.question if question is None else question
    judge = ctx.hit_cache.get("__bound_judge")
    for chunk in ranked:
        score = jaccard(gold, chunk.text)
        if score >= HIT_AT:
            flags.append(True)
            continue
        if score < MISS_BELOW:
            flags.append(False)
            continue
        key = (cache_prefix, ctx.judge_slot, chunk.chunk_key, chunk.rank, chunk.text)
        cached = ctx.hit_cache.get(key)
        if cached is None:
            verdict = judge.check_chunk_usefulness(asked, gold, chunk)
            cached = bool(verdict.useful)
            ctx.hit_cache[key] = cached
        flags.append(bool(cached))
    return flags


def first_hit_rank(chunks: list[Chunk], flags: list[bool]) -> int | None:
    ranked = sorted(chunks, key=lambda chunk: chunk.rank)
    for chunk, flag in zip(ranked, flags, strict=False):
        if flag:
            return chunk.rank
    return None
