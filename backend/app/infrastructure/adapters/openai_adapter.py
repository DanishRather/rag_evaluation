from __future__ import annotations

import os

from app.domain.errors import DomainError
from app.domain.models import AdapterBuild, Capabilities, QueryRequest, Trace
from app.infrastructure.adapters.http_client import safe_post
from app.infrastructure.adapters.mapper import error_trace, map_payload
from app.security.crypto import decrypt
from app.security.ssrf import assert_public_http


class OpenAIChatAdapter:
    """OpenAI-compatible chat completions. Chunks stay empty unless a JSONPath map is set."""

    def __init__(self, build: AdapterBuild, *, transport=None, resolver=None) -> None:
        self._settings = dict(build.settings)
        self._timeout = build.timeout_s
        self._transport = transport
        self._resolver = resolver
        self._secret = None
        if build.secret is not None:
            self._secret = decrypt(build.secret.ciphertext, build.secret.nonce)
        elif os.environ.get("OPENAI_API_KEY", "").strip():
            self._secret = os.environ["OPENAI_API_KEY"].strip()
        base = str(self._settings.get("base_url") or "").rstrip("/")
        if not base:
            raise DomainError("validation_error", "OpenAI adapter requires a base URL")
        self._url = base + "/chat/completions"
        assert_public_http(self._url, resolver)
        if not self._settings.get("model"):
            raise DomainError("validation_error", "OpenAI adapter requires a model name")

    def capabilities(self) -> Capabilities:
        mapping = self._settings.get("response_map") or {}
        return Capabilities(
            has_chunks="chunks" in mapping,
            has_scores="chunk_score" in mapping,
            has_rewritten_query="rewritten_query" in mapping,
            has_token_usage=True,
        )

    def run_query(self, request: QueryRequest) -> Trace:
        messages = [{"role": "user", "content": request.question}]
        body = {"model": self._settings["model"], "messages": messages, "temperature": 0}
        headers = {}
        if self._secret:
            headers["Authorization"] = f"Bearer {self._secret}"
        try:
            outcome = safe_post(
                self._url,
                body,
                headers,
                self._timeout,
                self._secret,
                transport=self._transport,
                resolver=self._resolver,
            )
        except DomainError:
            raise
        except Exception as exc:
            return error_trace(request, str(exc))
        if outcome.error or not isinstance(outcome.payload, dict):
            return error_trace(request, outcome.error or "Empty response", outcome.elapsed_ms)
        answer = _assistant_text(outcome.payload)
        usage = outcome.payload.get("usage") or {}
        mapped = map_payload(
            outcome.payload,
            self._settings.get("response_map") or {},
            request,
            latency_ms=outcome.elapsed_ms,
        )
        mapped.answer = answer
        if mapped.prompt_tokens is None:
            mapped.prompt_tokens = _int(usage.get("prompt_tokens"))
        if mapped.completion_tokens is None:
            mapped.completion_tokens = _int(usage.get("completion_tokens"))
        if mapped.model is None and outcome.payload.get("model"):
            mapped.model = str(outcome.payload["model"])
        return mapped


def _assistant_text(payload: dict) -> str:
    choices = payload.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content")
    return "" if content is None else str(content)


def _int(value) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
