from __future__ import annotations

from jsonpath_ng.ext import parse

from app.domain.models import Chunk, QueryRequest, Trace, new_id


def _values(payload: object, path: str | None) -> list:
    if not path or not isinstance(payload, (dict, list)):
        return []
    return [match.value for match in parse(path).find(payload)]


def _scalar(payload: object, path: str | None):
    found = _values(payload, path)
    return found[0] if found else None


def _as_int(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def map_payload(
    payload: object,
    mapping: dict | None,
    request: QueryRequest,
    *,
    latency_ms: float | None,
    error: str | None = None,
) -> Trace:
    mapping = mapping or {}
    answer = _scalar(payload, mapping.get("answer"))
    chunks = _chunks(payload, mapping)
    rewritten = _scalar(payload, mapping.get("rewritten_query"))
    mapped_latency = _as_float(_scalar(payload, mapping.get("latency_ms")))
    return Trace(
        id=new_id(),
        run_id="",
        test_case_id=request.test_case_id,
        conversation_id=request.conversation_id,
        turn_index=request.turn_index,
        kind="primary",
        repeat_index=0,
        question=request.question,
        answer=None if answer is None else str(answer),
        rewritten_query=None if rewritten is None else str(rewritten),
        error=error,
        latency_ms=latency_ms if mapped_latency is None else mapped_latency,
        prompt_tokens=_as_int(_scalar(payload, mapping.get("prompt_tokens"))),
        completion_tokens=_as_int(_scalar(payload, mapping.get("completion_tokens"))),
        model=None if _scalar(payload, mapping.get("model")) is None else str(_scalar(payload, mapping.get("model"))),
        status="error" if error else "ok",
        chunks=chunks,
    )


def _chunks(payload: object, mapping: dict) -> list[Chunk]:
    raw_items: list = []
    for value in _values(payload, mapping.get("chunks")):
        if isinstance(value, list):
            raw_items.extend(value)
        else:
            raw_items.append(value)
    chunks: list[Chunk] = []
    for index, item in enumerate(raw_items, start=1):
        if isinstance(item, str):
            text = item
            score = source = page = key = token_length = None
        elif isinstance(item, dict):
            text = _scalar(item, mapping.get("chunk_text") or "$.text")
            score = _as_float(_scalar(item, mapping.get("chunk_score")))
            source_value = _scalar(item, mapping.get("chunk_source"))
            source = None if source_value is None else str(source_value)
            page = _as_int(_scalar(item, mapping.get("chunk_page")))
            key_value = _scalar(item, mapping.get("chunk_id"))
            key = None if key_value is None else str(key_value)
            token_length = _as_int(_scalar(item, mapping.get("chunk_token_length")))
            text = "" if text is None else str(text)
        else:
            continue
        chunks.append(
            Chunk(
                chunk_key=key or f"chunk-{index}",
                rank=index,
                text=text or "",
                score=score,
                source=source,
                page=page,
                token_length=token_length,
            )
        )
    return chunks


def error_trace(request: QueryRequest, message: str, latency_ms: float | None = None) -> Trace:
    return Trace(
        id=new_id(),
        run_id="",
        test_case_id=request.test_case_id,
        conversation_id=request.conversation_id,
        turn_index=request.turn_index,
        kind="primary",
        repeat_index=0,
        question=request.question,
        answer=None,
        rewritten_query=None,
        error=message,
        latency_ms=latency_ms,
        prompt_tokens=None,
        completion_tokens=None,
        model=None,
        status="error",
        chunks=[],
    )
