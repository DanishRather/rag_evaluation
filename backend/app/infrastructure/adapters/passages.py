"""Turn an AgentOS run payload into the passages the evaluators can score."""

from __future__ import annotations

import re

from app.domain.models import Chunk
from app.domain.text import tokenize

_CITE = re.compile(r"(?=\[C\d+\])")
_KEY = re.compile(r"\[(C\d+)\]")
_FILE = re.compile(r"File:\s*(\S+)")
_STATUS = ("no passages found", "not a clause number", "document(s):")


def passages_from_agent(payload: object) -> list[Chunk]:
    if not isinstance(payload, dict):
        return []
    texts: list[tuple[str, str]] = []
    tools = payload.get("tools")
    if isinstance(tools, list):
        for tool in tools:
            if not isinstance(tool, dict):
                continue
            result = tool.get("result")
            if isinstance(result, str) and result.strip():
                texts.append((str(tool.get("tool_name") or ""), result))
    contexts = payload.get("contexts")
    if isinstance(contexts, list):
        for item in contexts:
            if isinstance(item, str) and item.strip():
                texts.append(("", item))
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    texts.append((str(item.get("source") or item.get("id") or ""), text))
    documents = _documents(payload.get("citations"))
    texts.extend(documents)
    return _chunks(texts)


def _documents(citations: object) -> list[tuple[str, str]]:
    if not isinstance(citations, dict):
        return []
    documents = citations.get("documents")
    if not isinstance(documents, list):
        return []
    found: list[tuple[str, str]] = []
    for item in documents:
        if not isinstance(item, dict):
            continue
        text = item.get("cited_text")
        if not isinstance(text, str) or not text.strip():
            continue
        source = item.get("file_name") or item.get("document_title") or ""
        found.append((str(source), text))
    return found


def _chunks(texts: list[tuple[str, str]]) -> list[Chunk]:
    ordered: list[Chunk] = []
    index_by_key: dict[str, int] = {}
    for source_name, text in texts:
        for piece in _pieces(text):
            if _is_status(piece):
                continue
            key_match = _KEY.search(piece)
            key = key_match.group(1) if key_match else ""
            file_match = _FILE.search(piece)
            source = file_match.group(1) if file_match else (source_name or None)
            chunk = Chunk(
                chunk_key=key or f"passage-{len(ordered) + 1}",
                rank=len(ordered) + 1,
                text=piece,
                score=None,
                source=source or None,
                page=None,
                token_length=len(tokenize(piece)),
            )
            if key and key in index_by_key:
                current = ordered[index_by_key[key]]
                if len(piece) > len(current.text):
                    chunk.rank = current.rank
                    ordered[index_by_key[key]] = chunk
                continue
            if key:
                index_by_key[key] = len(ordered)
            ordered.append(chunk)
    for rank, chunk in enumerate(ordered, start=1):
        chunk.rank = rank
        if not chunk.chunk_key.startswith("C") and not chunk.chunk_key.startswith("passage-"):
            chunk.chunk_key = f"passage-{rank}"
    return ordered


def _pieces(text: str) -> list[str]:
    parts = [part.strip() for part in _CITE.split(text) if part.strip()]
    kept: list[str] = []
    for part in parts:
        if part.lower().startswith("search:") and "[C" not in part:
            continue
        kept.append(part)
    return kept


def _is_status(text: str) -> bool:
    lowered = " ".join(text.lower().split())
    if any(marker in lowered for marker in _STATUS):
        return True
    return lowered.startswith("clause lookup:") and " no " in f" {lowered} "
