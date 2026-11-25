from __future__ import annotations

import json
import os
import re
from urllib.parse import urlparse

from jinja2 import Environment

from app.domain.errors import DomainError
from app.domain.models import AdapterBuild, Capabilities, QueryRequest, Trace
from app.infrastructure.adapters.http_client import safe_post
from app.infrastructure.adapters.mapper import error_trace, map_payload
from app.infrastructure.adapters.passages import passages_from_agent
from app.security.crypto import decrypt
from app.security.redact import redact
from app.security.ssrf import assert_public_http

_ENV = Environment(autoescape=False)
_DEFAULT_TEMPLATE = '{"question": {{ question | tojson }}, "conversation_id": {{ conversation_id | tojson }}}'
_AGENT_TEMPLATE = "message={{ question }}"
_QUESTION = re.compile(r"\{\{[^}]*\bquestion\b[^}]*\}\}")
_PAIRS = re.compile(r"[\r\n&]+")
_SAMPLE = QueryRequest(question='Sample "question" & more = test', conversation_id="sample")


def _token(build: AdapterBuild) -> str | None:
    if build.secret is not None:
        return decrypt(build.secret.ciphertext, build.secret.nonce)
    value = os.environ.get("OPENAI_API_KEY", "").strip()
    return value or None


class HttpAdapter:
    def __init__(self, build: AdapterBuild, *, transport=None, resolver=None) -> None:
        self._settings = _apply_agent_run(dict(build.settings))
        self._timeout = build.timeout_s
        self._transport = transport
        self._resolver = resolver
        self._secret = _token(build)
        url = str(self._settings.get("url") or "")
        if not url:
            raise DomainError("validation_error", "HTTP adapter requires a URL")
        assert_public_http(url, resolver)
        self._template = str(self._settings.get("request_template") or _DEFAULT_TEMPLATE)
        check_template(self._template)

    def capabilities(self) -> Capabilities:
        mapping = self._settings.get("response_map") or {}
        return Capabilities(
            has_chunks="chunks" in mapping,
            has_scores="chunk_score" in mapping,
            has_rewritten_query="rewritten_query" in mapping,
            has_token_usage="prompt_tokens" in mapping or "completion_tokens" in mapping,
        )

    def run_query(self, request: QueryRequest) -> Trace:
        url = str(self._settings["url"])
        try:
            body = render_body(self._template, request)
        except Exception as exc:
            return error_trace(request, redact(f"Request template failed: {exc}", self._secret))
        headers = {}
        if self._secret:
            headers["Authorization"] = f"Bearer {self._secret}"
        try:
            encoding = "form" if isinstance(body, dict) or self._settings.get("encoding") == "form" else "json"
            outcome = safe_post(
                url,
                body,
                headers,
                self._timeout,
                self._secret,
                transport=self._transport,
                resolver=self._resolver,
                encoding=encoding,
            )
        except DomainError:
            raise
        except Exception as exc:
            return error_trace(request, redact(str(exc), self._secret))
        if outcome.error:
            return error_trace(request, outcome.error, outcome.elapsed_ms)
        trace = map_payload(
            outcome.payload,
            self._settings.get("response_map") or {},
            request,
            latency_ms=outcome.elapsed_ms,
        )
        passages = passages_from_agent(outcome.payload)
        if passages and not any(chunk.score is not None for chunk in trace.chunks):
            trace.chunks = passages
        return trace


def _apply_agent_run(settings: dict) -> dict:
    """AgentOS run endpoints take curl -F 'message=<question>' and return content, not $.answer."""
    url = str(settings.get("url") or "")
    path = urlparse(url).path
    if "/agents/" not in path or not path.rstrip("/").endswith("/runs"):
        return settings
    settings = dict(settings)
    settings["encoding"] = "form"
    template = str(settings.get("request_template") or "")
    if not _QUESTION.search(template) or template.lstrip().startswith("{"):
        settings["request_template"] = _AGENT_TEMPLATE
    mapping = {
        "answer": "$.content",
        "chunks": "$.contexts[*]",
        "chunk_text": "$.text",
        "chunk_id": "$.id",
        "chunk_source": "$.source",
        "prompt_tokens": "$.metrics.input_tokens",
        "completion_tokens": "$.metrics.output_tokens",
        "model": "$.model",
    }
    supplied = dict(settings.get("response_map") or {})
    if supplied.get("answer") in (None, "", "$.answer"):
        supplied["answer"] = "$.content"
    mapping.update(supplied)
    settings["response_map"] = mapping
    return settings


def check_template(template: str) -> None:
    if not _QUESTION.search(template):
        raise DomainError(
            "validation_error",
            "Question body must include {{ question }}. A fixed text sends the same question for every dataset row.",
        )
    try:
        render_body(template, _SAMPLE)
    except json.JSONDecodeError as exc:
        raise DomainError(
            "validation_error",
            "Question body is not valid JSON once a question with quotes is filled in. "
            "Write {{ question | tojson }} without quotes around it.",
            {"detail": str(exc)},
        ) from exc
    except Exception as exc:
        raise DomainError("validation_error", f"Question body is not valid: {exc}") from exc


def render_body(template: str, request: QueryRequest) -> str | dict[str, str]:
    """A body starting with { renders to JSON text. Anything else is key=value form fields."""
    values = {"question": request.question, "conversation_id": request.conversation_id, "history": []}
    if template.lstrip().startswith("{"):
        rendered = _ENV.from_string(template).render(**values)
        if not isinstance(json.loads(rendered), dict):
            raise ValueError("the body must be a JSON object")
        return rendered
    fields: dict[str, str] = {}
    for part in _PAIRS.split(template):
        part = part.strip()
        if not part:
            continue
        key, separator, value = part.partition("=")
        if not separator or not key.strip():
            raise ValueError("write a JSON object or key=value pairs such as message={{ question }}")
        text = _ENV.from_string(value.strip()).render(**values)
        if len(text) >= 2 and text[0] == text[-1] == '"':
            try:
                text = json.loads(text)
            except json.JSONDecodeError:
                pass
        fields[key.strip()] = str(text)
    return fields
