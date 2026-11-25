"""HTTP calls with SSRF checks and credential stripping on redirects."""

from __future__ import annotations

import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx

from app.security.redact import redact
from app.security.ssrf import assert_public_http


@dataclass
class HttpOutcome:
    status_code: int | None
    payload: object
    error: str | None
    elapsed_ms: float


def safe_post(
    url: str,
    body: dict | str,
    headers: dict[str, str],
    timeout_s: float,
    secret: str | None,
    *,
    transport=None,
    resolver=None,
    encoding: str = "json",
) -> HttpOutcome:
    assert_public_http(url, resolver)
    started = time.perf_counter()
    current = dict(headers)
    target = url
    try:
        if encoding == "form":
            _form_fields(body)
    except ValueError as exc:
        return HttpOutcome(None, None, str(exc), 0)
    try:
        with httpx.Client(timeout=timeout_s, transport=transport, follow_redirects=False) as client:
            for _hop in range(5):
                assert_public_http(target, resolver)
                response = client.post(target, **_request_kwargs(body, current, encoding))
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        break
                    nxt = urljoin(target, location)
                    if urlparse(nxt).netloc != urlparse(target).netloc:
                        current.pop("Authorization", None)
                        current.pop("authorization", None)
                    target = nxt
                    continue
                elapsed = (time.perf_counter() - started) * 1000
                if response.status_code >= 400:
                    return HttpOutcome(
                        response.status_code,
                        None,
                        redact(f"HTTP {response.status_code}: {response.text[:500]}", secret),
                        elapsed,
                    )
                payload, error = _read_payload(response)
                if error:
                    return HttpOutcome(response.status_code, payload, redact(error, secret), elapsed)
                return HttpOutcome(response.status_code, payload, None, elapsed)
    except httpx.TimeoutException:
        elapsed = (time.perf_counter() - started) * 1000
        return HttpOutcome(None, None, "Target timed out", elapsed)
    except httpx.HTTPError as exc:
        elapsed = (time.perf_counter() - started) * 1000
        return HttpOutcome(None, None, redact(str(exc), secret), elapsed)
    elapsed = (time.perf_counter() - started) * 1000
    return HttpOutcome(None, None, "Too many redirects", elapsed)


def _content(body: dict | str) -> bytes:
    if isinstance(body, str):
        return body.encode()
    import json

    return json.dumps(body).encode()


def _json_headers(headers: dict[str, str]) -> dict[str, str]:
    merged = {"content-type": "application/json", "accept": "application/json"}
    merged.update(headers)
    return merged


def _request_kwargs(body: dict | str, headers: dict[str, str], encoding: str) -> dict:
    if encoding == "form":
        kept = {key: value for key, value in headers.items() if key.lower() != "content-type"}
        kept.setdefault("accept", "application/json")
        # (None, value) is a form field, the same shape as curl -F 'name=value'.
        files = [(key, (None, value)) for key, value in _form_fields(body).items()]
        return {"files": files, "headers": kept}
    return {"content": _content(body), "headers": _json_headers(headers)}


def _form_fields(body: dict | str) -> dict[str, str]:
    if isinstance(body, str):
        payload = _form_payload(body)
    else:
        payload = body
    if not isinstance(payload, dict):
        raise ValueError("Form body must be a JSON object")
    fields: dict[str, str] = {}
    for key, value in payload.items():
        if value is None:
            continue
        if isinstance(value, bool):
            fields[str(key)] = "true" if value else "false"
        else:
            fields[str(key)] = str(value)
    fields.setdefault("stream", "false")
    return fields


def _read_payload(response) -> tuple[object, str | None]:
    raw = response.text
    content_type = response.headers.get("content-type", "")
    if "text/event-stream" in content_type or raw.lstrip().startswith("event:"):
        payload = parse_event_stream(raw)
        if not str(payload.get("content") or "").strip():
            return payload, "Agent stream ended without an answer"
        return payload, None
    try:
        return response.json(), None
    except Exception:
        return None, "Response was not JSON"


def parse_event_stream(text: str) -> dict:
    """Turn an AgentOS event stream into the JSON shape the response map reads."""
    import json

    events: list[dict] = []
    name = "message"
    data: list[str] = []

    def flush() -> None:
        nonlocal name, data
        if not data:
            name = "message"
            return
        raw = "\n".join(data)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"content": raw}
        if isinstance(payload, dict):
            payload.setdefault("event", name)
            events.append(payload)
        name = "message"
        data = []

    for line in text.splitlines():
        if line.startswith("event:"):
            flush()
            name = line.split(":", 1)[1].strip() or "message"
        elif line.startswith("data:"):
            data.append(line.split(":", 1)[1].lstrip())
        elif not line.strip():
            flush()
    flush()

    completed = [item for item in events if item.get("event") == "RunCompleted"]
    final = completed[-1] if completed else {}
    content = final.get("content")
    if not isinstance(content, str) or not content.strip():
        parts = [item.get("content") for item in events if item.get("event") == "RunContent"]
        content = "".join(part for part in parts if isinstance(part, str))
    metrics = final.get("metrics") if isinstance(final.get("metrics"), dict) else {}
    model = final.get("model")
    if not model:
        for item in events:
            if item.get("model"):
                model = item["model"]
                break
    contexts: list[dict] = []
    for item in events:
        if item.get("event") != "ToolCallCompleted":
            continue
        tool = item.get("tool") if isinstance(item.get("tool"), dict) else {}
        result = tool.get("result")
        if not isinstance(result, str) or not result.strip():
            continue
        tool_name = str(tool.get("tool_name") or "tool")
        contexts.append({"id": tool_name, "text": result, "source": tool_name})
    return {
        "content": content if isinstance(content, str) else "",
        "model": None if model is None else str(model),
        "metrics": {
            "input_tokens": metrics.get("input_tokens"),
            "output_tokens": metrics.get("output_tokens"),
        },
        "contexts": contexts,
    }


def _form_payload(body: str) -> dict:
    import json
    from urllib.parse import parse_qsl

    text = body.strip()
    if text.startswith("{") or text.startswith("["):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError("Form body must be a JSON object") from exc
        if not isinstance(payload, dict):
            raise ValueError("Form body must be a JSON object")
        return payload
    if "=" in text:
        return dict(parse_qsl(text, keep_blank_values=True))
    raise ValueError("Form body must be a JSON object or key=value pairs")
