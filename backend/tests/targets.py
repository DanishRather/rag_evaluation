from app.domain.models import Capabilities, QueryRequest, Trace, new_id


class DemoTarget:
    def capabilities(self) -> Capabilities:
        return Capabilities(False, False, False, False)

    def run_query(self, request: QueryRequest) -> Trace:
        if request.question == "fail":
            raise RuntimeError("target down")
        return Trace(
            id=new_id(),
            run_id="",
            test_case_id=request.test_case_id,
            conversation_id=request.conversation_id,
            turn_index=request.turn_index,
            kind="primary",
            repeat_index=0,
            question=request.question,
            answer="30 days",
            rewritten_query=None,
            error=None,
            latency_ms=4,
            prompt_tokens=None,
            completion_tokens=None,
            model=None,
            status="ok",
        )
