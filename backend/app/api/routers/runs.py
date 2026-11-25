from typing import Annotated

from fastapi import APIRouter, Depends, Header
from fastapi.responses import StreamingResponse

from app.api.deps import get_run_service
from app.domain.models import JudgeConfig, RunSpec
from app.schemas.http import (
    EstimateRequest,
    EstimateResponse,
    JudgeDefaultsResponse,
    MetricRowResponse,
    MetricsResponse,
    ReevaluateRequest,
    RunCreate,
    RunLiveResponse,
    RunResponse,
    TraceResponse,
)
from app.services.run_service import RunService

router = APIRouter(prefix="/runs", tags=["runs"])


def _judge(body) -> JudgeConfig:
    secondary = None if body.secondary is None else _judge(body.secondary)
    return JudgeConfig(provider=body.provider, model_id=body.model_id, temperature=0, secondary=secondary)


def _run(run) -> RunResponse:
    return RunResponse(
        id=run.id,
        project_id=run.project_id,
        dataset_id=run.dataset_id,
        system_config_version_id=run.system_config_version_id,
        replay_of_run_id=run.replay_of_run_id,
        status=run.status,
        repeats=run.repeats,
        max_concurrency=run.max_concurrency,
        judge_config=run.judge_config,
        evaluator_ids=list(run.evaluator_ids),
        use_judge_cache=bool(run.use_judge_cache),
        created_at=run.created_at,
    )


def _trace(trace) -> TraceResponse:
    return TraceResponse(
        id=trace.id,
        run_id=trace.run_id,
        test_case_id=trace.test_case_id,
        conversation_id=trace.conversation_id,
        turn_index=trace.turn_index,
        kind=trace.kind,
        repeat_index=trace.repeat_index,
        question=trace.question,
        answer=trace.answer,
        rewritten_query=trace.rewritten_query,
        error=trace.error,
        status=trace.status,
        latency_ms=trace.latency_ms,
        prompt_tokens=trace.prompt_tokens,
        completion_tokens=trace.completion_tokens,
        model=trace.model,
        chunks=[
            {
                "chunk_key": chunk.chunk_key,
                "rank": chunk.rank,
                "text": chunk.text,
                "score": chunk.score,
                "source": chunk.source,
                "page": chunk.page,
                "token_length": chunk.token_length,
            }
            for chunk in trace.chunks
        ],
    )


@router.get("/judge-defaults", response_model=JudgeDefaultsResponse)
def judge_defaults(service: RunService = Depends(get_run_service)):
    defaults = service.judge_defaults()
    return JudgeDefaultsResponse(provider=defaults.provider, model_id=defaults.model_id)


@router.post("/estimate", response_model=EstimateResponse)
def estimate(body: EstimateRequest, service: RunService = Depends(get_run_service)):
    result = service.estimate(body.dataset_id, body.system_config_version_id, _judge(body.judge), body.repeats)
    return EstimateResponse(
        target_calls=result.target_calls,
        counterfactual_calls=result.counterfactual_calls,
        judge_calls=result.judge_calls,
        notes=result.notes,
    )


@router.post("", response_model=RunResponse)
def create_run(
    body: RunCreate,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    service: RunService = Depends(get_run_service),
):
    spec = RunSpec(
        project_id=body.project_id,
        dataset_id=body.dataset_id,
        system_config_version_id=body.system_config_version_id,
        judge=_judge(body.judge),
        repeats=body.repeats,
        max_concurrency=body.max_concurrency,
        price_table=body.price_table,
        use_judge_cache=body.use_judge_cache,
        target_timeout_s=body.target_timeout_s,
        target_max_attempts=body.target_max_attempts,
        evaluator_ids=body.evaluator_ids,
    )
    return _run(service.start(spec, idempotency_key))


@router.get("", response_model=list[RunResponse])
def list_runs(project_id: str | None = None, limit: int = 20, service: RunService = Depends(get_run_service)):
    return [_run(run) for run in service.list_runs(project_id, limit)]


@router.get("/{run_id}", response_model=RunResponse)
def get_run(run_id: str, service: RunService = Depends(get_run_service)):
    return _run(service.get(run_id))


@router.get("/{run_id}/live", response_model=RunLiveResponse)
def live(run_id: str, service: RunService = Depends(get_run_service)):
    return RunLiveResponse(**service.live(run_id))


@router.delete("/failed")
def delete_failed_runs(service: RunService = Depends(get_run_service)):
    return {"deleted": service.delete_failed()}


@router.delete("/{run_id}", status_code=204)
def delete_run(run_id: str, service: RunService = Depends(get_run_service)):
    service.delete(run_id)


@router.post("/{run_id}/cancel", response_model=RunResponse)
def cancel_run(run_id: str, service: RunService = Depends(get_run_service)):
    return _run(service.cancel(run_id))


@router.post("/{run_id}/resume", response_model=RunResponse)
def resume_run(run_id: str, service: RunService = Depends(get_run_service)):
    return _run(service.resume(run_id))


@router.post("/{run_id}/reevaluate", response_model=RunResponse)
def reevaluate(run_id: str, body: ReevaluateRequest, service: RunService = Depends(get_run_service)):
    judge = None if body.judge is None else _judge(body.judge)
    return _run(service.reevaluate(run_id, judge, body.repeats, body.use_judge_cache))


@router.get("/{run_id}/events")
def events(run_id: str, service: RunService = Depends(get_run_service)):
    return StreamingResponse(service.stream_events(run_id), media_type="text/event-stream")


@router.get("/{run_id}/traces", response_model=list[TraceResponse])
def list_traces(run_id: str, service: RunService = Depends(get_run_service)):
    return [_trace(trace) for trace in service.list_traces(run_id)]


@router.get("/{run_id}/metrics", response_model=MetricsResponse)
def get_metrics(run_id: str, service: RunService = Depends(get_run_service)):
    payload = service.get_metrics(run_id)
    return MetricsResponse(
        rows=[
            MetricRowResponse(
                id=row.id,
                run_id=row.run_id,
                test_case_id=row.test_case_id,
                metric_id=row.metric_id,
                value=row.value,
                status=row.status,
                skip_reason=row.skip_reason,
                details=row.details,
                rubric_version=row.rubric_version,
                judge_model=row.judge_model,
                temperature=row.temperature,
                judge_role=row.judge_role,
                prompt_hash=row.prompt_hash,
                repeat_index=row.repeat_index,
                judge_slot=row.judge_slot,
            )
            for row in payload["rows"]
        ],
        summary=payload["summary"],
    )
