import httpx
import pytest

from app.domain.errors import DomainError
from app.domain.models import AdapterBuild, Capabilities, QueryRequest, Secret, Trace, new_id
from app.infrastructure.adapters.http_adapter import HttpAdapter
from app.infrastructure.adapters.openai_adapter import OpenAIChatAdapter
from app.infrastructure.adapters.python_adapter import PythonObjectAdapter
from app.main import default_adapters
from app.security.crypto import encrypt
from tests.fakes import ScriptAdapter

PUBLIC = "http://rag.example/query"


def public_resolver(host, port, *_args, **_kwargs):
    return [(2, 1, 6, "", ("8.8.8.8", port or 80))]


def private_resolver(host, port, *_args, **_kwargs):
    return [(2, 1, 6, "", ("10.1.2.3", port or 80))]


def _request(question="What is the refund window?") -> QueryRequest:
    return QueryRequest(question=question, test_case_id="case-1", turn_index=0)


def _assert_contract(adapter, request: QueryRequest):
    ok = adapter.run_query(request)
    assert isinstance(ok, Trace)
    assert ok.status == "ok"
    failed = adapter.run_query(QueryRequest(question="fail", test_case_id="case-2"))
    assert isinstance(failed, Trace)
    assert failed.status == "error"
    assert failed.error
    caps = adapter.capabilities()
    assert caps.has_chunks is bool(ok.chunks)
    assert caps.has_scores is any(chunk.score is not None for chunk in ok.chunks)
    assert caps.has_rewritten_query is bool(ok.rewritten_query)
    if caps.has_token_usage:
        assert ok.prompt_tokens is not None or ok.completion_tokens is not None


def test_fake_adapter_contract():
    def handler(request: QueryRequest) -> Trace:
        if request.question == "fail":
            return Trace(
                id=new_id(),
                run_id="",
                test_case_id=request.test_case_id,
                conversation_id=None,
                turn_index=0,
                kind="primary",
                repeat_index=0,
                question=request.question,
                answer=None,
                rewritten_query=None,
                error="down",
                latency_ms=1,
                prompt_tokens=None,
                completion_tokens=None,
                model=None,
                status="error",
            )
        return Trace(
            id=new_id(),
            run_id="",
            test_case_id=request.test_case_id,
            conversation_id=None,
            turn_index=0,
            kind="primary",
            repeat_index=0,
            question=request.question,
            answer="30 days",
            rewritten_query=None,
            error=None,
            latency_ms=1,
            prompt_tokens=None,
            completion_tokens=None,
            model=None,
            status="ok",
        )

    _assert_contract(ScriptAdapter(handler, Capabilities(False, False, False, False)), _request())


def test_http_adapter_contract_and_redacts_secrets(monkeypatch):
    monkeypatch.setenv("EVAL_SECRET_KEY", "test-secret-key")
    ciphertext, nonce = encrypt("super-secret-token")
    secret = Secret(id="sec", project_id="p", ciphertext=ciphertext, nonce=nonce)

    def handler(request: httpx.Request) -> httpx.Response:
        if b"fail" in request.content:
            return httpx.Response(500, text="bearer super-secret-token failed")
        return httpx.Response(
            200,
            json={
                "answer": "30 days",
                "contexts": [{"id": "c1", "text": "alpha beta", "score": 0.9, "source": "policy.md", "page": 1}],
                "rewritten_query": "refund window",
                "usage": {"prompt_tokens": 11, "completion_tokens": 4},
                "model": "target-model",
            },
        )

    adapter = HttpAdapter(
        AdapterBuild(
            settings={
                "url": PUBLIC,
                "response_map": {
                    "answer": "$.answer",
                    "chunks": "$.contexts[*]",
                    "chunk_text": "$.text",
                    "chunk_id": "$.id",
                    "chunk_score": "$.score",
                    "chunk_source": "$.source",
                    "chunk_page": "$.page",
                    "rewritten_query": "$.rewritten_query",
                    "prompt_tokens": "$.usage.prompt_tokens",
                    "completion_tokens": "$.usage.completion_tokens",
                    "model": "$.model",
                },
            },
            secret=secret,
            timeout_s=5,
        ),
        transport=httpx.MockTransport(handler),
        resolver=public_resolver,
    )
    _assert_contract(adapter, _request())
    failed = adapter.run_query(QueryRequest(question="fail"))
    assert "super-secret-token" not in (failed.error or "")
    assert "[redacted]" in (failed.error or "")


def test_openai_adapter_contract(monkeypatch):
    monkeypatch.setenv("EVAL_SECRET_KEY", "test-secret-key")

    def handler(request: httpx.Request) -> httpx.Response:
        if b"fail" in request.content:
            return httpx.Response(500, text="nope")
        return httpx.Response(
            200,
            json={
                "model": "target-model",
                "choices": [{"message": {"role": "assistant", "content": "30 days"}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 2},
            },
        )

    adapter = OpenAIChatAdapter(
        AdapterBuild(
            settings={"base_url": "http://rag.example/v1", "model": "target-model"},
            secret=None,
            timeout_s=5,
        ),
        transport=httpx.MockTransport(handler),
        resolver=public_resolver,
    )
    _assert_contract(adapter, _request())


def test_python_adapter_contract(monkeypatch):
    monkeypatch.setenv("EVAL_ALLOW_PYTHON_ADAPTERS", "1")
    adapter = PythonObjectAdapter(AdapterBuild(settings={"import_path": "tests.targets:DemoTarget"}, secret=None, timeout_s=5))
    _assert_contract(adapter, _request())


def test_private_and_metadata_urls_are_rejected_before_a_request(monkeypatch):
    monkeypatch.delenv("EVAL_ALLOW_LOOPBACK", raising=False)
    requested = {"count": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        requested["count"] += 1
        return httpx.Response(200, json={"answer": "no"})

    transport = httpx.MockTransport(handler)
    for url in ("http://127.0.0.1/query", "http://169.254.169.254/latest", "http://10.0.0.8/query"):
        with pytest.raises(DomainError) as caught:
            HttpAdapter(
                AdapterBuild(settings={"url": url}, secret=None, timeout_s=5),
                transport=transport,
                resolver=public_resolver,
            )
        assert caught.value.code == "adapter_rejected"
    with pytest.raises(DomainError) as caught:
        HttpAdapter(
            AdapterBuild(settings={"url": "http://internal.example/query"}, secret=None, timeout_s=5),
            transport=transport,
            resolver=private_resolver,
        )
    assert caught.value.code == "adapter_rejected"
    assert requested["count"] == 0


def test_loopback_is_allowed_only_when_the_flag_is_set(monkeypatch):
    monkeypatch.delenv("EVAL_ALLOW_LOOPBACK", raising=False)
    requested = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        requested["count"] += 1
        assert request.headers["content-type"].startswith("multipart/form-data")
        assert b'name="message"' in request.content
        assert b"What does Article 10.7" in request.content
        assert b'name="stream"' in request.content
        assert b"false" in request.content
        return httpx.Response(200, json={"content": "the clause"})

    transport = httpx.MockTransport(handler)
    url = "http://127.0.0.1:8000/agents/query-agent/runs"
    with pytest.raises(DomainError) as caught:
        HttpAdapter(
            AdapterBuild(settings={"url": url, "encoding": "form"}, secret=None, timeout_s=5),
            transport=transport,
        )
    assert caught.value.code == "adapter_rejected"
    assert requested["count"] == 0

    monkeypatch.setenv("EVAL_ALLOW_LOOPBACK", "1")
    adapter = HttpAdapter(
        AdapterBuild(
            settings={
                "url": url,
                "encoding": "form",
                "request_template": '{"message": {{ question | tojson }}, "stream": false}',
                "response_map": {"answer": "$.content"},
            },
            secret=None,
            timeout_s=5,
        ),
        transport=transport,
    )
    trace = adapter.run_query(_request("What does Article 10.7 of the KG-D6 PSC say?"))
    assert trace.status == "ok"
    assert trace.answer == "the clause"
    assert requested["count"] == 1
    with pytest.raises(DomainError):
        HttpAdapter(
            AdapterBuild(settings={"url": "http://10.0.0.8/query"}, secret=None, timeout_s=5),
            transport=transport,
        )


def test_form_post_sends_stream_false_when_the_template_omits_it():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.content
        return httpx.Response(200, json={"content": "ok"})

    adapter = HttpAdapter(
        AdapterBuild(
            settings={
                "url": PUBLIC,
                "encoding": "form",
                "request_template": '{"message": {{ question | tojson }}}',
                "response_map": {"answer": "$.content"},
            },
            secret=None,
            timeout_s=5,
        ),
        transport=httpx.MockTransport(handler),
        resolver=public_resolver,
    )
    trace = adapter.run_query(_request("ping"))
    assert trace.status == "ok"
    assert trace.answer == "ok"
    assert b'name="message"' in seen["body"]
    assert b"ping" in seen["body"]
    assert b'name="stream"' in seen["body"]
    assert b"false" in seen["body"]


def test_key_value_body_is_posted_as_form_fields_and_keeps_the_question_whole():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["type"] = request.headers["content-type"]
        seen["body"] = request.content
        return httpx.Response(200, json={"content": "ok"})

    adapter = HttpAdapter(
        AdapterBuild(
            settings={
                "url": PUBLIC,
                "encoding": "json",
                "request_template": "message={{ question }}",
                "response_map": {"answer": "$.content"},
            },
            secret=None,
            timeout_s=5,
        ),
        transport=httpx.MockTransport(handler),
        resolver=public_resolver,
    )
    trace = adapter.run_query(_request("Terms & conditions = what?"))
    assert trace.status == "ok"
    assert trace.answer == "ok"
    assert seen["type"].startswith("multipart/form-data")
    assert b'name="message"' in seen["body"]
    assert b"Terms & conditions = what?" in seen["body"]
    assert b'name="stream"' in seen["body"]
    assert b"false" in seen["body"]


def test_agent_run_curl_reads_the_stream_and_tool_results(monkeypatch):
    monkeypatch.setenv("EVAL_ALLOW_LOOPBACK", "1")
    sse = "\n".join(
        [
            "event: RunStarted",
            'data: {"event":"RunStarted","model":"gpt-test"}',
            "",
            "event: ToolCallCompleted",
            'data: {"event":"ToolCallCompleted","tool":{"tool_name":"search_documents","result":"Article 10.7 allows 180 days."}}',
            "",
            "event: RunCompleted",
            'data: {"event":"RunCompleted","content":"Article 10.7 allows 180 days.","metrics":{"input_tokens":12,"output_tokens":4}}',
            "",
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["content-type"].startswith("multipart/form-data")
        assert b'name="message"' in request.content
        assert b"Article 10.7" in request.content
        return httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})

    adapter = HttpAdapter(
        AdapterBuild(
            settings={
                "url": "http://127.0.0.1:8000/agents/query-agent/runs",
                "encoding": "json",
                "request_template": '{"question": {{ question | tojson }}, "history": {{ history | tojson }}}',
                "response_map": {"answer": "$.answer", "chunks": "$.contexts[*]", "chunk_text": "$.text"},
            },
            secret=None,
            timeout_s=5,
        ),
        transport=httpx.MockTransport(handler),
    )
    trace = adapter.run_query(_request("What does Article 10.7 of the KG-D6 PSC say?"))
    assert trace.status == "ok"
    assert trace.answer == "Article 10.7 allows 180 days."
    assert trace.prompt_tokens == 12
    assert trace.completion_tokens == 4
    assert trace.model == "gpt-test"
    assert [chunk.text for chunk in trace.chunks] == ["Article 10.7 allows 180 days."]


def test_agent_json_keeps_search_passages_and_drops_empty_lookups(monkeypatch):
    monkeypatch.setenv("EVAL_ALLOW_LOOPBACK", "1")
    body = {
        "content": "Article 320(2) requires joint recruitment.",
        "model": "gpt-test",
        "metrics": {"input_tokens": 3, "output_tokens": 2},
        "tools": [
            {"tool_name": "get_clause", "result": "Clause lookup: 320(2). No passages found."},
            {"tool_name": "list_documents", "result": "1 document(s): constitution.pdf"},
            {
                "tool_name": "search_documents",
                "result": (
                    "Search: article 320\n\n"
                    "[C217] Constitution\nFile: constitution.pdf\n"
                    "It shall also be the duty of the Union Public Service Commission.\n\n"
                    "[C16] preamble only"
                ),
            },
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    adapter = HttpAdapter(
        AdapterBuild(
            settings={
                "url": "http://127.0.0.1:8000/agents/query-agent/runs",
                "encoding": "form",
                "request_template": "message={{ question }}",
                "response_map": {"answer": "$.content"},
            },
            secret=None,
            timeout_s=5,
        ),
        transport=httpx.MockTransport(handler),
    )
    trace = adapter.run_query(_request("What does Article 320(2) require?"))
    assert [chunk.chunk_key for chunk in trace.chunks] == ["C217", "C16"]
    assert trace.chunks[0].source == "constitution.pdf"
    assert "Union Public Service Commission" in trace.chunks[0].text
    assert trace.answer == "Article 320(2) requires joint recruitment."


@pytest.mark.parametrize(
    "template",
    ["ping", '{"message": "ping"}', "message=ping", '{"message": "{{ question }}"}', "{{ question }}"],
)
def test_bodies_that_cannot_send_each_question_are_rejected(template):
    with pytest.raises(DomainError) as caught:
        HttpAdapter(
            AdapterBuild(settings={"url": PUBLIC, "request_template": template}, secret=None, timeout_s=5),
            resolver=public_resolver,
        )
    assert caught.value.code == "validation_error"


def test_python_adapter_is_absent_unless_the_flag_is_set(monkeypatch):
    monkeypatch.delenv("EVAL_ALLOW_PYTHON_ADAPTERS", raising=False)
    assert "python" not in default_adapters()
    monkeypatch.setenv("EVAL_ALLOW_PYTHON_ADAPTERS", "1")
    assert "python" in default_adapters()
