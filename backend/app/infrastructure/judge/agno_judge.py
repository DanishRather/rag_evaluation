"""Agno implementation of the Judge port. This module is the only importer of Agno."""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from typing import Any

from app.domain.errors import DomainError, JudgeOutputError
from app.domain.models import Chunk, Finding, JudgeConfig, JudgeProvenance, JudgeUsage, JudgeVerdict, new_id
from app.domain.verdicts import (
    CorrectnessVerdict,
    FaithfulnessVerdict,
    ReportProse,
    RewriteVerdict,
    SplitVerdict,
    UsefulnessVerdict,
)
from app.infrastructure.judge.rubrics import RUBRICS

_omit_lock = threading.Lock()
_omit_temperature: dict[str, float] = {}

_SCHEMAS = {
    "correctness": CorrectnessVerdict,
    "faithfulness": FaithfulnessVerdict,
    "usefulness": UsefulnessVerdict,
    "split_confirm": SplitVerdict,
    "rewrite": RewriteVerdict,
    "report": ReportProse,
}


def default_runner(agent_name: str, schema: type, prompt: str, config: JudgeConfig, instructions: str):
    from agno.agent import Agent
    from agno.models.openai import OpenAIChat, OpenAIResponses

    models = {"openai_chat": OpenAIChat, "openai_responses": OpenAIResponses}
    model_cls = models[config.provider]
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise DomainError("validation_error", "Set OPENAI_API_KEY in the environment. The UI does not send it.")

    def attempt(temperature: float | None):
        model = _openai_model(model_cls, config.model_id, api_key, temperature, with_retries=True)
        parser = _openai_model(model_cls, config.model_id, api_key, temperature, with_retries=False)
        agent = Agent(
            name=agent_name,
            model=model,
            instructions=instructions,
            output_schema=schema,
            parser_model=parser,
            parser_model_prompt="Map the previous reply onto the schema. Do not add facts.",
            markdown=False,
            retries=1,
        )
        return agent.run(prompt)

    with _omit_lock:
        accepted = _omit_temperature.get(config.model_id)
    if accepted is not None:
        return _stamp_temperature(attempt(None), accepted)
    try:
        result = attempt(0)
    except Exception as exc:
        if not temperature_rejected(str(exc)):
            raise
        accepted = _accepted_temperature(str(exc))
        _remember_temperature(config.model_id, accepted)
        return _stamp_temperature(attempt(None), accepted)
    if temperature_rejected(_result_text(result)):
        accepted = _accepted_temperature(_result_text(result)) or 1
        _remember_temperature(config.model_id, accepted)
        return _stamp_temperature(attempt(None), accepted)
    return _stamp_temperature(result, 0)


def _openai_model(model_cls, model_id: str, api_key: str, temperature: float | None, *, with_retries: bool):
    kwargs = {"id": model_id, "api_key": api_key}
    if temperature is not None:
        kwargs["temperature"] = temperature
    if with_retries:
        kwargs.update(retries=2, delay_between_retries=1, exponential_backoff=True, cache_response=False)
    return model_cls(**kwargs)


def _remember_temperature(model_id: str, temperature: float) -> None:
    with _omit_lock:
        _omit_temperature[model_id] = temperature


def temperature_rejected(text: str) -> bool:
    lowered = text.lower()
    return "temperature" in lowered and ("does not support" in lowered or "unsupported value" in lowered)


def _accepted_temperature(text: str) -> float:
    match = re.search(r"default \(([-0-9.]+)\)", text)
    if match:
        return float(match.group(1))
    return 1


def _result_text(result: object) -> str:
    parts = [getattr(result, "content", ""), getattr(result, "error", ""), result]
    return " ".join(str(part) for part in parts if part is not None)


def _stamp_temperature(result: object, temperature: float):
    try:
        setattr(result, "eval_temperature", temperature)
    except Exception:
        return result
    return result


class AgnoJudge:
    def __init__(self, repository, runner=None) -> None:
        self._repository = repository
        self._runner = runner or default_runner
        self._config: JudgeConfig | None = None
        self._repeats = 1
        self._cache_on = False
        self._slot = "primary"
        self._run_id = ""
        self._memory: dict[str, Any] = {}
        self._cross: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._call_temperature = threading.local()

    def prepare(
        self,
        config: JudgeConfig,
        *,
        repeats: int,
        use_judge_cache: bool,
        role: str,
        run_id: str,
    ) -> None:
        self._config = config
        self._repeats = repeats
        self._cache_on = bool(use_judge_cache) and repeats == 1
        self._slot = role
        self._run_id = run_id
        with self._lock:
            self._memory.clear()

    def provenance(self, agent: str) -> JudgeProvenance:
        version, _body, digest = load_rubric(agent)
        config = self._config
        return JudgeProvenance(
            rubric_version=version,
            model_id="" if config is None else config.model_id,
            temperature=getattr(self._call_temperature, "value", 0),
            prompt_hash=digest,
            judge_role=agent,
            judge_slot=self._slot,
        )

    def check_correctness(self, question: str, expected_answer: str, actual_answer: str) -> CorrectnessVerdict:
        prompt = (
            f"Question:\n{question}\n\nExpected answer:\n{expected_answer}\n\nActual answer:\n{actual_answer}"
        )
        canonical = {"question": question, "expected_answer": expected_answer, "actual_answer": actual_answer}
        return self._invoke("correctness", CorrectnessVerdict, prompt, canonical)

    def check_faithfulness(self, actual_answer: str, chunks: list[Chunk]) -> FaithfulnessVerdict:
        rendered = [
            {"chunk_id": chunk.chunk_key, "rank": chunk.rank, "text": chunk.text} for chunk in chunks
        ]
        prompt = "Actual answer:\n" + actual_answer + "\n\nChunks:\n" + json.dumps(rendered, ensure_ascii=False)
        verdict = self._invoke(
            "faithfulness",
            FaithfulnessVerdict,
            prompt,
            {"actual_answer": actual_answer, "chunks": rendered},
        )
        if any(claim.supported and not (claim.chunk_id or "").strip() for claim in verdict.claims):
            raise JudgeOutputError(verdict)
        return verdict

    def check_chunk_usefulness(self, question: str, gold_passage: str, chunk: Chunk) -> UsefulnessVerdict:
        key = _hash(
            {
                "slot": self._slot,
                "model": None if self._config is None else self._config.model_id,
                "question": question,
                "gold": gold_passage,
                "chunk": chunk.chunk_key,
                "text": chunk.text,
            }
        )
        with self._lock:
            remembered = self._memory.get(key)
        if remembered is not None:
            return remembered
        prompt = (
            f"Question:\n{question}\n\nGold passage:\n{gold_passage}\n\n"
            f"Chunk {chunk.chunk_key} rank {chunk.rank}:\n{chunk.text}"
        )
        verdict = self._invoke(
            "usefulness",
            UsefulnessVerdict,
            prompt,
            {"question": question, "gold_passage": gold_passage, "chunk": chunk.text, "key": chunk.chunk_key},
        )
        with self._lock:
            self._memory[key] = verdict
        return verdict

    def confirm_chunk_split(self, gold_passage: str, neighbors: list[Chunk]) -> SplitVerdict:
        rendered = [{"rank": chunk.rank, "text": chunk.text} for chunk in neighbors]
        prompt = "Gold passage:\n" + gold_passage + "\n\nNeighbors:\n" + json.dumps(rendered, ensure_ascii=False)
        return self._invoke(
            "split_confirm",
            SplitVerdict,
            prompt,
            {"gold_passage": gold_passage, "neighbors": rendered},
        )

    def rewrite_standalone(self, history: list[dict], follow_up: str) -> RewriteVerdict:
        prompt = "Prior turns:\n" + json.dumps(history, ensure_ascii=False) + f"\n\nFollow-up:\n{follow_up}"
        return self._invoke("rewrite", RewriteVerdict, prompt, {"history": history, "follow_up": follow_up})

    def write_report(self, findings: list[Finding]) -> ReportProse:
        payload = [
            {
                "id": finding.id,
                "rule_id": finding.rule_id,
                "cause": finding.cause,
                "severity": finding.severity,
                "count": finding.count,
            }
            for finding in findings
        ]
        prompt = "Findings:\n" + json.dumps(payload, ensure_ascii=False)
        return self._invoke("report", ReportProse, prompt, {"findings": payload})

    def _invoke(self, agent: str, schema: type, prompt: str, canonical: dict):
        config = self._config
        if config is None:
            raise JudgeOutputError("Judge is not prepared")
        _, instructions, digest = load_rubric(agent)
        full_prompt = f"{instructions}\n\n{prompt}"
        cache_key = _hash(
            {
                "prompt": full_prompt,
                "input": canonical,
                "model": config.model_id,
                "temperature": 0,
                "slot": self._slot,
                "agent": agent,
            }
        )
        if self._cache_on:
            cached = self._cached(cache_key)
            if cached is not None:
                self._record(agent, 0, 0, None, None, True)
                return schema.model_validate(cached)
        result = self._runner(agent, schema, full_prompt, config, instructions)
        used = getattr(result, "eval_temperature", None)
        if isinstance(used, (int, float)):
            self._call_temperature.value = float(used)
        content = getattr(result, "content", result)
        if not isinstance(content, schema):
            retry = full_prompt + "\n\nThe previous reply was not valid schema content:\n" + repr(content)
            result = self._runner(agent, schema, retry, config, instructions)
            used = getattr(result, "eval_temperature", None)
            if isinstance(used, (int, float)):
                self._call_temperature.value = float(used)
            content = getattr(result, "content", result)
            if not isinstance(content, schema):
                raise JudgeOutputError(content)
        self._record_result(agent, result)
        dumped = content.model_dump()
        if self._cache_on:
            with self._lock:
                self._cross[cache_key] = dumped
        self._save_verdict(cache_key, agent, digest, dumped)
        return content

    def _cached(self, cache_key: str) -> dict | None:
        with self._lock:
            cached = self._cross.get(cache_key)
        if cached is not None:
            return cached
        stored = self._load_verdict(cache_key)
        if stored is None:
            return None
        with self._lock:
            self._cross[cache_key] = stored
        return stored

    def _load_verdict(self, cache_key: str) -> dict | None:
        if self._repository is None:
            return None
        rows = self._repository.list(JudgeVerdict, cache_key=cache_key)
        if not rows:
            return None
        return rows[0].verdict

    def _save_verdict(self, cache_key: str, agent: str, digest: str, verdict: dict) -> None:
        if self._repository is None or self._load_verdict(cache_key) is not None:
            return
        config = self._config
        self._repository.add(
            JudgeVerdict(
                id=new_id(),
                cache_key=cache_key,
                agent=agent,
                model_id="" if config is None else config.model_id,
                judge_slot=self._slot,
                prompt_hash=digest,
                verdict=verdict,
            )
        )

    def _record_result(self, agent: str, result: object) -> None:
        metrics = getattr(result, "metrics", None)
        self._record(
            agent,
            _metric(metrics, "input_tokens"),
            _metric(metrics, "output_tokens"),
            _metric(metrics, "cost"),
            _metric(metrics, "duration"),
            False,
        )

    def _record(self, agent: str, input_tokens, output_tokens, cost, duration, cache_hit: bool) -> None:
        if not self._run_id or self._repository is None:
            return
        config = self._config
        self._repository.add(
            JudgeUsage(
                id=new_id(),
                run_id=self._run_id,
                test_case_id="",
                agent=agent,
                judge_slot=self._slot,
                model_id="" if config is None else config.model_id,
                input_tokens=None if input_tokens is None else int(input_tokens),
                output_tokens=None if output_tokens is None else int(output_tokens),
                cost=None if cost is None else float(cost),
                duration=None if duration is None else float(duration),
                cache_hit=cache_hit,
            )
        )


def load_rubric(agent: str) -> tuple[int, str, str]:
    version, instructions = RUBRICS[agent]
    # Same bytes as the old frontmatter files, so stored prompt hashes stay valid.
    text = f"---\nversion: {version}\n---\n{instructions}\n"
    digest = hashlib.sha256(text.encode()).hexdigest()
    return version, instructions, digest


def _hash(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def _metric(metrics: object, name: str):
    if metrics is None:
        return None
    if isinstance(metrics, dict):
        return metrics.get(name)
    return getattr(metrics, name, None)
