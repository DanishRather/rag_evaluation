from __future__ import annotations

import asyncio
import json
import os
import re
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

from app.domain.errors import DomainError
from app.domain.models import (
    AdapterBuild,
    Capabilities,
    Dataset,
    Estimate,
    EvalContext,
    Job,
    JudgeConfig,
    JudgeUsage,
    MetricResult,
    ProgressEvent,
    QueryRequest,
    RewriteRecord,
    Run,
    RunSpec,
    Secret,
    System,
    SystemConfig,
    TestCase,
    Trace,
    WorkerState,
    canonical_hash,
    new_id,
    utc_now,
)
from app.domain.verdicts import RewriteVerdict
from app.evaluators.summary import summarize
from app.services.cleanup import purge_run
from app.services.lookup import require

_BACKOFF = (1, 2, 4, 8, 16)
_TERMINAL = {"succeeded", "failed", "cancelled"}
_QUESTION = re.compile(r"\{\{[^}]*\bquestion\b[^}]*\}\}")
_FIXED_CONNECTION = (
    "This connection sends one fixed text instead of each question from the file. "
    "Open Connect, save the connection again, click Use on it, then start a new run. "
    "Resume keeps the old connection, so it cannot fix this."
)
_NO_ANSWERS = (
    "This run stored no answer from the endpoint, so there is nothing to judge again. "
    "Start a new run after the connection is saved."
)
_JUDGED = frozenset(
    {
        "correctness",
        "faithfulness",
        "hit",
        "mrr",
        "precision_at_k",
        "recall_at_k",
        "chunk_split",
    }
)
_PROVIDERS = frozenset({"openai_chat", "openai_responses"})
_ANSWER_PREVIEW = 280
_LOG_TAIL = 40


def conversation_groups(cases: list[TestCase]) -> list[list[TestCase]]:
    ordered = sorted(cases, key=lambda case: case.source_row)
    groups: dict[str, list[TestCase]] = {}
    order: list[str] = []
    for case in ordered:
        key = case.conversation_id or f"single:{case.id}"
        if key not in groups:
            order.append(key)
            groups[key] = []
        groups[key].append(case)
    return [groups[key] for key in order]


def top_k_of(config: SystemConfig) -> int:
    raw = (config.profile_settings or {}).get("top_k")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 5
    return value if value > 0 else 5


class RunService:
    def __init__(
        self,
        repository,
        job_queue,
        judge,
        secondary_judge,
        adapter_factories: dict,
        evaluator_factory,
        diagnosis,
        reports,
        sleep=None,
        worker: WorkerState | None = None,
    ) -> None:
        self._repository = repository
        self._queue = job_queue
        self._judge = judge
        self._secondary = secondary_judge
        self._adapters = adapter_factories
        self._evaluator_factory = evaluator_factory
        self._diagnosis = diagnosis
        self._reports = reports
        self._sleep = sleep or time.sleep
        self._worker = worker or WorkerState()

    def judge_defaults(self) -> JudgeConfig:
        provider = os.environ.get("EVAL_JUDGE_PROVIDER", "openai_chat").strip() or "openai_chat"
        if provider not in _PROVIDERS:
            provider = "openai_chat"
        return JudgeConfig(
            provider=provider,
            model_id=os.environ.get("EVAL_JUDGE_MODEL", "").strip(),
            temperature=0,
        )

    def estimate(self, dataset_id: str, system_config_id: str, judge: JudgeConfig, repeats: int) -> Estimate:
        judge = self._with_env_model(judge)
        self._check_judge(judge)
        if repeats < 1:
            raise DomainError("validation_error", "Repeats must be at least 1")
        config = require(self._repository, SystemConfig, system_config_id, "System config")
        cases = self._repository.list(TestCase, dataset_id=dataset_id)
        if not cases:
            raise DomainError("validation_error", "Dataset has no cases")
        judges = 2 if judge.secondary else 1
        followups = sum(1 for case in cases if case.turn_index > 0)
        expected = sum(1 for case in cases if (case.expected_answer or "").strip())
        gold = sum(1 for case in cases if (case.gold_passage or "").strip())
        k = top_k_of(config)
        notes = [
            "Failures and skips reduce the actual counts.",
            "Faithfulness skips cases whose chunk list is empty after the run.",
            "Usefulness calls only the gray band, not every chunk.",
            "Split confirm calls only uncertain splits.",
            "A secondary judge doubles correctness, faithfulness, usefulness, and split confirm. It does not double rewrite, the report writer, or target calls.",
        ]
        return Estimate(
            target_calls=len(cases) * repeats,
            counterfactual_calls=followups * repeats,
            judge_calls={
                "correctness": expected * repeats * judges,
                "faithfulness": len(cases) * repeats * judges,
                "usefulness_worst_case": gold * k * repeats * judges,
                "split_confirm_worst_case": gold * repeats * judges,
                "rewrite": followups,
                "report_writer": 1,
            },
            notes=notes,
        )

    def start(self, spec: RunSpec, idempotency_key: str | None) -> Run:
        spec = replace(spec, judge=self._with_env_model(spec.judge))
        self._validate_spec(spec)
        self._require_each_question(spec.system_config_version_id)
        request_hash = canonical_hash(spec.hash_payload())
        if idempotency_key:
            existing = self._repository.list(Run, idempotency_key=idempotency_key)
            if existing:
                if existing[0].request_hash != request_hash:
                    raise DomainError(
                        "idempotency_conflict",
                        "Idempotency key was already used with a different request",
                    )
                return existing[0]
        run = self._build_run(spec, idempotency_key, request_hash, replay_of=None)
        self._repository.add(run)
        self._queue.enqueue(run.id)
        return run

    def reevaluate(self, run_id: str, judge: JudgeConfig | None, repeats: int | None, use_judge_cache: bool | None) -> Run:
        original = require(self._repository, Run, run_id, "Run")
        root_id = original.replay_of_run_id or original.id
        stored = [
            trace
            for trace in self._repository.list(Trace, run_id=root_id)
            if trace.kind == "primary" and trace.status == "ok" and trace.answer
        ]
        if not stored:
            raise DomainError("validation_error", _NO_ANSWERS)
        chosen = self._with_env_model(judge or JudgeConfig.from_dict(original.judge_config))
        self._check_judge(chosen)
        spec = RunSpec(
            project_id=original.project_id,
            dataset_id=original.dataset_id,
            system_config_version_id=original.system_config_version_id,
            judge=chosen,
            repeats=repeats or original.repeats,
            max_concurrency=original.max_concurrency,
            price_table=original.price_table,
            use_judge_cache=original.use_judge_cache if use_judge_cache is None else use_judge_cache,
            target_timeout_s=original.target_timeout_s,
            target_max_attempts=original.target_max_attempts,
            evaluator_ids=list(original.evaluator_ids),
        )
        self._validate_spec(spec)
        run = self._build_run(spec, None, canonical_hash(spec.hash_payload()), replay_of=root_id)
        root = require(self._repository, Run, root_id, "Run")
        run.capabilities = dict(root.capabilities or {})
        self._repository.add(run)
        self._queue.enqueue(run.id)
        return run

    def get(self, run_id: str) -> Run:
        return require(self._repository, Run, run_id, "Run")

    def list_runs(self, project_id: str | None = None, limit: int = 20) -> list[Run]:
        runs = self._repository.list(Run, project_id=project_id) if project_id else self._repository.list(Run)
        return list(reversed(runs))[: max(1, limit)]

    def live(self, run_id: str) -> dict:
        run = self.get(run_id)
        cases = self._repository.list(TestCase, dataset_id=run.dataset_id)
        ordered = [case for group in conversation_groups(cases) for case in group]
        events = self._repository.list(ProgressEvent, run_id=run.id)
        states = _question_states(events)
        root = run.replay_of_run_id or run.id
        answers = {
            (trace.test_case_id, trace.repeat_index): trace
            for trace in self._repository.list(Trace, run_id=root)
            if trace.kind == "primary"
        }
        terminal = run.status in _TERMINAL
        items: list[dict] = []
        for case in ordered:
            for repeat_index in range(max(1, run.repeats)):
                seen = states.get((case.id, repeat_index), {})
                trace = answers.get((case.id, repeat_index))
                state = seen.get("state", "queued")
                if terminal and state == "queued":
                    state = "not_run"
                elif terminal and state in {"calling", "judging"}:
                    state = "stopped"
                error = seen.get("error")
                if error is None and trace is not None and trace.status != "ok":
                    error = trace.error
                items.append(
                    {
                        "position": len(items) + 1,
                        "test_case_id": case.id,
                        "source_row": case.source_row,
                        "question": case.question,
                        "conversation_id": case.conversation_id,
                        "turn_index": case.turn_index,
                        "repeat_index": repeat_index,
                        "state": state,
                        "stage": seen.get("stage"),
                        "started_at": seen.get("started_at"),
                        "stage_started_at": seen.get("stage_started_at"),
                        "finished_at": seen.get("finished_at"),
                        "attempt": seen.get("attempt"),
                        "max_attempts": run.target_max_attempts,
                        "last_error": seen.get("last_error"),
                        "error": error,
                        "cause": seen.get("cause"),
                        "latency_ms": None if trace is None else trace.latency_ms,
                        "answer": None if trace is None else _preview(trace.answer),
                    }
                )
        counts = Counter(item["state"] for item in items)
        done = counts["done"]
        failed = counts["failed"]
        jobs = self._repository.list(Job)
        mine = next((job for job in jobs if job.run_id == run.id), None)
        busy = [job.run_id for job in jobs if job.status == "running" and job.run_id != run.id]
        runs_ahead = 0
        if mine is not None and mine.status == "queued":
            runs_ahead = len(busy) + sum(
                1 for job in jobs if job.status == "queued" and job.created_at < mine.created_at
            )
        return {
            "run_id": run.id,
            "status": run.status,
            "message": events[-1].message if events else "",
            "total": len(items),
            "done": done,
            "failed": failed,
            "running": counts["calling"] + counts["judging"],
            "waiting": counts["queued"],
            "remaining": len(items) - done - failed,
            "max_concurrency": run.max_concurrency,
            "target_timeout_s": run.target_timeout_s,
            "runs_ahead": runs_ahead,
            "busy_run_ids": busy,
            "worker": {
                "embedded": self._worker.embedded,
                "alive": self._worker.alive,
                "current_run_id": self._worker.current_run_id,
                "heartbeat": self._worker.heartbeat,
            },
            "items": items,
            "log": [
                {
                    "seq": event.seq,
                    "kind": event.kind,
                    "message": event.message,
                    "at": (event.payload or {}).get("at"),
                    "test_case_id": (event.payload or {}).get("test_case_id"),
                }
                for event in events[-_LOG_TAIL:]
            ],
        }

    def cancel(self, run_id: str) -> Run:
        run = self.get(run_id)
        if run.status == "succeeded":
            raise DomainError("validation_error", "Run has already finished")
        if run.status in {"cancelled", "failed"}:
            raise DomainError(
                "validation_error",
                "This run has already stopped. Cancel only stops a run that is queued or still calling the endpoint. Delete it to clear it from the list.",
            )
        jobs = self._repository.list(Job, run_id=run_id)
        if run.status == "queued":
            run.status = "cancelled"
            self._repository.add(run)
            if jobs:
                jobs[0].status = "cancelled"
                self._repository.add(jobs[0])
            self._progress(run, "run_cancelled", "Run cancelled")
            return run
        run.status = "cancel_requested"
        self._repository.add(run)
        if jobs:
            jobs[0].status = "cancel_requested"
            self._repository.add(jobs[0])
        return run

    def resume(self, run_id: str) -> Run:
        run = self.get(run_id)
        if run.status == "succeeded":
            raise DomainError(
                "validation_error",
                "This run already finished. Start a new run to call the endpoint again, or use Re-evaluate to judge the stored answers.",
            )
        if run.status == "running":
            raise DomainError("validation_error", "This run is already running. Cancel it if you want it to stop.")
        if run.status == "queued":
            return run
        self._require_each_question(run.system_config_version_id)
        run.status = "queued"
        self._repository.add(run)
        self._queue.enqueue(run.id)
        return run

    def delete(self, run_id: str) -> None:
        run = self.get(run_id)
        if run.status not in _TERMINAL:
            raise DomainError("validation_error", "Cancel the run and wait until it stops before deleting it.")
        for replay in self._repository.list(Run):
            if replay.replay_of_run_id == run.id and replay.id != run.id:
                purge_run(self._repository, replay.id)
        purge_run(self._repository, run.id)

    def delete_failed(self) -> int:
        failed = [run for run in self._repository.list(Run) if run.status in {"failed", "cancelled"}]
        for run in failed:
            purge_run(self._repository, run.id)
        return len(failed)

    def list_traces(self, run_id: str) -> list[Trace]:
        run = self.get(run_id)
        root = run.replay_of_run_id or run.id
        return self._repository.list(Trace, run_id=root)

    def get_metrics(self, run_id: str) -> dict:
        self.get(run_id)
        rows = self._repository.list(MetricResult, run_id=run_id)
        return {"rows": rows, "summary": summarize(rows)}

    def events_after(self, run_id: str, seq: int) -> list[ProgressEvent]:
        self.get(run_id)
        return [event for event in self._repository.list(ProgressEvent, run_id=run_id) if event.seq > seq]

    def stream_events(self, run_id: str):
        self.get(run_id)
        return self._iter_events(run_id)

    async def _iter_events(self, run_id: str):
        cursor = 0
        while True:
            batch = self.events_after(run_id, cursor)
            for event in batch:
                cursor = event.seq
                yield "data: " + json.dumps(_event_dict(event)) + "\n\n"
            current = self.get(run_id)
            if current.status in _TERMINAL and not self.events_after(run_id, cursor):
                break
            await asyncio.sleep(0.5)

    def execute(self, run_id: str) -> None:
        run = self.get(run_id)
        if run.status == "cancel_requested":
            self._finish_cancel(run)
            return
        run.status = "running"
        self._repository.add(run)
        self._progress(run, "progress", "Run started")
        try:
            if run.replay_of_run_id:
                self._execute_replay(run)
            else:
                self._execute_live(run)
            run = self.get(run.id)
            if run.status in {"cancel_requested", "cancelled"}:
                self._finish_cancel(run)
                return
            self._reports.write(run.id)
            run = self.get(run.id)
            run.status = "succeeded"
            self._repository.add(run)
            self._finish_job(run.id, "succeeded")
            self._progress(run, "run_finished", "Run finished")
        except Exception as exc:
            current = self._repository.get(Run, run_id)
            if current is not None and current.status in {"cancel_requested", "cancelled"}:
                self._finish_cancel(current)
                return
            if current is not None:
                current.status = "failed"
                self._repository.add(current)
                self._finish_job(run_id, "failed")
                reason = getattr(exc, "message", None) or str(exc) or type(exc).__name__
                self._progress(current, "run_failed", f"Run failed: {reason}")
            raise exc

    def _execute_live(self, run: Run) -> None:
        config = require(self._repository, SystemConfig, run.system_config_version_id, "System config")
        secret = None if not config.secret_id else self._repository.get(Secret, config.secret_id)
        adapter = self._open_adapter(config, secret, run.target_timeout_s)
        run.capabilities = adapter.capabilities().to_dict()
        self._repository.add(run)
        cases = self._repository.list(TestCase, dataset_id=run.dataset_id)
        self._score_groups(run, cases, adapter, live=True)

    def _execute_replay(self, run: Run) -> None:
        cases = self._repository.list(TestCase, dataset_id=run.dataset_id)
        self._score_groups(run, cases, adapter=None, live=False)

    def _score_groups(self, run: Run, cases: list[TestCase], adapter, live: bool) -> None:
        config = require(self._repository, SystemConfig, run.system_config_version_id, "System config")
        judge_config = JudgeConfig.from_dict(run.judge_config)
        self._judge.prepare(
            judge_config,
            repeats=run.repeats,
            use_judge_cache=run.use_judge_cache,
            role="primary",
            run_id=run.id,
        )
        if judge_config.secondary is not None:
            self._secondary.prepare(
                judge_config.secondary,
                repeats=run.repeats,
                use_judge_cache=run.use_judge_cache,
                role="secondary",
                run_id=run.id,
            )
        selected = set(run.evaluator_ids)
        primary = [item for item in self._evaluator_factory(self._judge) if item.id in selected]
        secondary = []
        if judge_config.secondary is not None:
            secondary = [
                item
                for item in self._evaluator_factory(self._secondary)
                if item.id in selected and item.id in _JUDGED
            ]
        groups = conversation_groups(cases)
        if not groups:
            self._aggregate(run, [], [])
            return
        workers = max(1, min(run.max_concurrency, len(groups)))

        def run_group(group: list[TestCase]):
            if self._cancelled(run.id):
                return []
            history: list[dict] = []
            produced: list[MetricResult] = []
            for case in group:
                if self._cancelled(run.id):
                    break
                ok_trace = None
                for repeat_index in range(run.repeats):
                    if self._cancelled(run.id):
                        break
                    rows = self._score_turn(
                        run,
                        case,
                        history,
                        adapter,
                        live,
                        repeat_index,
                        primary,
                        secondary,
                        config,
                    )
                    produced.extend(rows)
                    if ok_trace is None:
                        ok_trace = self._stored_trace(run, case.id, "primary", repeat_index, live)
                        if ok_trace is not None and ok_trace.status != "ok":
                            ok_trace = None
                if ok_trace is not None and ok_trace.status == "ok":
                    history.append(
                        {
                            "turn_index": case.turn_index,
                            "question": case.question,
                            "answer": ok_trace.answer or "",
                        }
                    )
            return produced

        with ThreadPoolExecutor(max_workers=workers) as pool:
            grouped = list(pool.map(run_group, groups))
        if self._cancelled(run.id):
            return
        flat = [row for batch in grouped for row in batch]
        self._aggregate(run, flat, cases)

    def _score_turn(self, run, case, history, adapter, live, repeat_index, primary, secondary, config):
        where = {"test_case_id": case.id, "repeat_index": repeat_index}
        if live:
            trace = self._existing(run.id, case.id, "primary", repeat_index)
            if trace is not None and trace.status == "ok":
                existing_metrics = self._case_metrics(run.id, case.id, repeat_index)
                if existing_metrics:
                    self._progress(run, "question_scored", "Already scored", where)
                    return existing_metrics
                self._progress(run, "question_started", "Judging the stored answer", {**where, "stage": "judging"})
            else:
                self._progress(run, "question_started", "Calling the endpoint", {**where, "stage": "target"})
                trace = self._call_target(adapter, case, run, repeat_index, "primary", case.question)
                trace.run_id = run.id
                self._repository.add(trace)
                self._progress(run, "trace_stored", "Answer received", {**where, "kind": "primary"})
        else:
            trace = self._existing(run.replay_of_run_id, case.id, "primary", repeat_index)
            if trace is None:
                return []
            self._progress(run, "question_started", "Judging the stored answer", {**where, "stage": "judging"})
        if trace.status != "ok":
            self._progress(run, "question_failed", trace.error or "Target error", where)
            return []
        counterfactual = None
        rewrite = None
        if case.turn_index > 0:
            counterfactual, rewrite = self._counterfactual(run, case, history, adapter, live, repeat_index, trace)
        capabilities = Capabilities.from_dict(run.capabilities)
        context = EvalContext(
            test_case=case,
            primary=trace,
            counterfactual=counterfactual if counterfactual and counterfactual.status == "ok" else None,
            prior_turns=list(history),
            capabilities=capabilities,
            top_k=top_k_of(config),
            repeat_index=repeat_index,
            judge_slot="primary",
            score_run_id=run.id,
            rewrite=rewrite,
        )
        results: list[MetricResult] = []
        for evaluator in primary:
            results.extend(evaluator.run(context))
        if secondary:
            secondary_context = replace(context, judge_slot="secondary", judge_role="secondary", hit_cache={})
            for evaluator in secondary:
                results.extend(evaluator.run(secondary_context))
        for row in results:
            self._repository.add(row)
        cause = self._diagnosis.cause_for(case, results)
        self._progress(
            run,
            "question_scored",
            cause or "Question scored",
            {"test_case_id": case.id, "cause": cause, "repeat_index": repeat_index},
        )
        return results

    def _counterfactual(self, run, case, history, adapter, live, repeat_index, primary):
        if live:
            stored = self._existing(run.id, case.id, "standalone_counterfactual", repeat_index)
            if stored is not None and stored.status == "ok":
                record = self._rewrite_record(run.id, case.id, repeat_index)
                return stored, _verdict_from(record, stored)
            verdict = self._judge.rewrite_standalone(history, case.question)
            self._progress(
                run,
                "question_started",
                "Calling the endpoint with the standalone rewrite",
                {"test_case_id": case.id, "repeat_index": repeat_index, "stage": "counterfactual"},
            )
            self._repository.add(
                RewriteRecord(
                    id=new_id(),
                    run_id=run.id,
                    test_case_id=case.id,
                    repeat_index=repeat_index,
                    standalone_question=verdict.standalone_question,
                    resolved_pronouns=verdict.resolved_pronouns,
                    reason=verdict.reason,
                )
            )
            trace = self._call_target(
                adapter,
                case,
                run,
                repeat_index,
                "standalone_counterfactual",
                verdict.standalone_question,
                fresh=True,
            )
            trace.run_id = run.id
            trace.kind = "standalone_counterfactual"
            self._repository.add(trace)
            self._progress(
                run,
                "trace_stored",
                "Counterfactual trace stored",
                {"test_case_id": case.id, "repeat_index": repeat_index, "kind": "standalone_counterfactual"},
            )
            return trace, verdict
        stored = self._existing(run.replay_of_run_id, case.id, "standalone_counterfactual", repeat_index)
        record = self._rewrite_record(run.replay_of_run_id, case.id, repeat_index)
        return stored, _verdict_from(record, stored)

    def _aggregate(self, run: Run, case_metrics: list[MetricResult], cases: list[TestCase]) -> None:
        root = run.replay_of_run_id or run.id
        traces = self._repository.list(Trace, run_id=root)
        usage = self._repository.list(JudgeUsage, run_id=run.id)
        judge_config = JudgeConfig.from_dict(run.judge_config)
        extras = {
            "run_id": run.id,
            "traces": traces,
            "price_table": run.price_table,
            "judge_usage": usage,
            "repeats": run.repeats,
            "has_secondary": judge_config.secondary is not None,
            "capabilities": Capabilities.from_dict(run.capabilities),
        }
        selected = set(run.evaluator_ids)
        evaluators = [item for item in self._evaluator_factory(self._judge) if item.id in selected]
        for evaluator in evaluators:
            for row in evaluator.aggregate([], case_metrics, extras):
                self._repository.add(row)
        _ = cases

    def _call_target(self, adapter, case, run, repeat_index, kind, question, *, fresh: bool = False) -> Trace:
        request = QueryRequest(
            question=question,
            history=[],
            test_case_id=case.id,
            conversation_id=None if fresh else case.conversation_id,
            turn_index=case.turn_index,
        )
        attempts = max(1, int(run.target_max_attempts))
        last = None
        for attempt in range(attempts):
            try:
                trace = adapter.run_query(request)
            except DomainError as exc:
                trace = Trace(
                    id=new_id(),
                    run_id=run.id,
                    test_case_id=case.id,
                    conversation_id=case.conversation_id,
                    turn_index=case.turn_index,
                    kind=kind,
                    repeat_index=repeat_index,
                    question=question,
                    answer=None,
                    rewritten_query=None,
                    error=exc.message,
                    latency_ms=None,
                    prompt_tokens=None,
                    completion_tokens=None,
                    model=None,
                    status="error",
                )
            trace.run_id = run.id
            trace.kind = kind
            trace.repeat_index = repeat_index
            trace.test_case_id = case.id
            last = trace
            if trace.status == "ok" or attempt == attempts - 1:
                return trace
            delay = _BACKOFF[min(attempt, len(_BACKOFF) - 1)]
            self._progress(
                run,
                "question_retry",
                f"Attempt {attempt + 1} of {attempts} failed: {trace.error or 'Target error'}. Retrying in {delay}s",
                {
                    "test_case_id": case.id,
                    "repeat_index": repeat_index,
                    "kind": kind,
                    "attempt": attempt + 2,
                    "error": trace.error,
                },
            )
            self._sleep(delay)
        return last

    def _case_metrics(self, run_id: str, test_case_id: str, repeat_index: int) -> list[MetricResult]:
        return [
            row
            for row in self._repository.list(MetricResult, run_id=run_id)
            if row.test_case_id == test_case_id and row.repeat_index == repeat_index and row.test_case_id != ""
        ]

    def _existing(self, run_id: str | None, test_case_id: str, kind: str, repeat_index: int) -> Trace | None:
        if not run_id:
            return None
        rows = [
            trace
            for trace in self._repository.list(Trace, run_id=run_id)
            if trace.test_case_id == test_case_id and trace.kind == kind and trace.repeat_index == repeat_index
        ]
        return rows[0] if rows else None

    def _stored_trace(self, run: Run, test_case_id: str, kind: str, repeat_index: int, live: bool):
        owner = run.id if live else run.replay_of_run_id
        return self._existing(owner, test_case_id, kind, repeat_index)

    def _rewrite_record(self, run_id: str, test_case_id: str, repeat_index: int):
        rows = [
            row
            for row in self._repository.list(RewriteRecord, run_id=run_id)
            if row.test_case_id == test_case_id and row.repeat_index == repeat_index
        ]
        return rows[0] if rows else None

    def _open_adapter(self, config: SystemConfig, secret, timeout_s: float):
        try:
            factory = self._adapters[config.adapter_type]
        except KeyError as exc:
            raise DomainError("validation_error", "Unknown adapter type") from exc
        return factory(AdapterBuild(settings=dict(config.adapter_settings), secret=secret, timeout_s=timeout_s))

    def _require_each_question(self, config_id: str) -> None:
        config = require(self._repository, SystemConfig, config_id, "System config")
        if config.adapter_type != "http":
            return
        template = str((config.adapter_settings or {}).get("request_template") or "")
        if template and _QUESTION.search(template) is None:
            raise DomainError("validation_error", _FIXED_CONNECTION)

    def _validate_spec(self, spec: RunSpec) -> None:
        self._check_judge(spec.judge)
        if spec.repeats < 1:
            raise DomainError("validation_error", "Repeats must be at least 1")
        if spec.max_concurrency < 1:
            raise DomainError("validation_error", "Concurrency must be at least 1")
        dataset_cases = self._repository.list(TestCase, dataset_id=spec.dataset_id)
        if not dataset_cases:
            raise DomainError("validation_error", "Dataset has no cases")
        dataset = require(self._repository, Dataset, spec.dataset_id, "Dataset")
        config = require(self._repository, SystemConfig, spec.system_config_version_id, "System config")
        system = require(self._repository, System, config.system_id, "System")
        if dataset.project_id != spec.project_id or system.project_id != spec.project_id:
            raise DomainError("validation_error", "Dataset and system must belong to the project")
        known = {item.id for item in self._evaluator_factory(self._judge)}
        if spec.evaluator_ids:
            unknown = [item for item in spec.evaluator_ids if item not in known]
            if unknown:
                raise DomainError("validation_error", "Unknown evaluator id", {"ids": unknown})

    def _with_env_model(self, judge: JudgeConfig) -> JudgeConfig:
        if str(judge.model_id).strip():
            return judge
        model_id = os.environ.get("EVAL_JUDGE_MODEL", "").strip()
        if not model_id:
            return judge
        provider = os.environ.get("EVAL_JUDGE_PROVIDER", "").strip() or judge.provider
        return replace(judge, provider=provider, model_id=model_id)

    def _check_judge(self, judge: JudgeConfig) -> None:
        if judge.provider not in _PROVIDERS or not str(judge.model_id).strip():
            raise DomainError(
                "validation_error",
                "Judge provider and model id are required. Set EVAL_JUDGE_MODEL or send a model id.",
            )
        if judge.secondary is not None:
            self._check_judge(judge.secondary)

    def _build_run(self, spec: RunSpec, idempotency_key: str | None, request_hash: str, replay_of: str | None) -> Run:
        known = [item.id for item in self._evaluator_factory(self._judge)]
        return Run(
            id=new_id(),
            project_id=spec.project_id,
            dataset_id=spec.dataset_id,
            system_config_version_id=spec.system_config_version_id,
            replay_of_run_id=replay_of,
            judge_config=spec.judge.to_dict(),
            evaluator_ids=list(spec.evaluator_ids or known),
            price_table=spec.price_table,
            repeats=spec.repeats,
            max_concurrency=spec.max_concurrency,
            status="queued",
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            use_judge_cache=spec.use_judge_cache,
            target_timeout_s=spec.target_timeout_s,
            target_max_attempts=spec.target_max_attempts,
            capabilities={},
            created_at=utc_now(),
        )

    def _cancelled(self, run_id: str) -> bool:
        run = self._repository.get(Run, run_id)
        return run is not None and run.status in {"cancel_requested", "cancelled"}

    def _finish_cancel(self, run: Run) -> None:
        run.status = "cancelled"
        self._repository.add(run)
        self._finish_job(run.id, "cancelled")
        self._progress(run, "run_cancelled", "Run cancelled")

    def _finish_job(self, run_id: str, status: str) -> None:
        jobs = self._repository.list(Job, run_id=run_id)
        if not jobs:
            return
        jobs[0].status = status
        self._repository.add(jobs[0])

    def _progress(self, run: Run, kind: str, message: str, payload: dict | None = None) -> None:
        self._repository.add(
            ProgressEvent(
                id=new_id(),
                run_id=run.id,
                seq=0,
                kind=kind,
                message=message,
                payload={**(payload or {}), "at": utc_now()},
            )
        )


def _question_states(events: list[ProgressEvent]) -> dict[tuple[str, int], dict]:
    """Fold progress events, in seq order, into the latest state of each question and repeat."""
    states: dict[tuple[str, int], dict] = {}
    for event in events:
        payload = event.payload or {}
        case_id = payload.get("test_case_id")
        if not case_id:
            continue
        key = (str(case_id), int(payload.get("repeat_index") or 0))
        item = states.setdefault(key, {})
        at = payload.get("at")
        if event.kind == "question_started":
            stage = payload.get("stage") or "target"
            if stage != "counterfactual":
                item.update(started_at=at, finished_at=None, error=None, last_error=None, cause=None, attempt=1)
            item.update(state="judging" if stage == "judging" else "calling", stage=stage, stage_started_at=at)
        elif event.kind == "question_retry":
            item.update(attempt=payload.get("attempt"), last_error=payload.get("error") or event.message)
        elif event.kind == "trace_stored":
            item.update(state="judging", stage="judging", stage_started_at=at)
        elif event.kind == "question_scored":
            item.update(state="done", stage=None, finished_at=at, cause=payload.get("cause"))
        elif event.kind == "question_failed":
            item.update(state="failed", stage=None, finished_at=at, error=event.message)
    return states


def _preview(text: str | None) -> str | None:
    if text is None:
        return None
    return text if len(text) <= _ANSWER_PREVIEW else text[: _ANSWER_PREVIEW - 1] + "…"


def _verdict_from(record: RewriteRecord | None, trace: Trace | None) -> RewriteVerdict | None:
    if record is None:
        if trace is None:
            return None
        return RewriteVerdict(standalone_question=trace.question, resolved_pronouns=False, reason="")
    return RewriteVerdict(
        standalone_question=record.standalone_question,
        resolved_pronouns=record.resolved_pronouns,
        reason=record.reason,
    )


def _event_dict(event: ProgressEvent) -> dict:
    return {
        "id": event.id,
        "run_id": event.run_id,
        "seq": event.seq,
        "kind": event.kind,
        "message": event.message,
        "payload": event.payload,
    }
