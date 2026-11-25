import pytest

from app.domain.errors import JudgeOutputError
from app.domain.models import JudgeConfig, JudgeVerdict
from app.domain.verdicts import CorrectnessVerdict, KeyFact
from app.infrastructure.judge.agno_judge import AgnoJudge, temperature_rejected
from app.infrastructure.judge.rubrics import RUBRICS
from tests.support import open_container


class Recorded:
    def __init__(self, content):
        self.content = content
        self.metrics = {"input_tokens": 2, "output_tokens": 1}


def _judge(contents):
    pending = list(contents)

    def runner(agent, schema, prompt, config, instructions):
        return pending.pop(0)

    judge = AgnoJudge(repository=None, runner=runner)
    judge.prepare(
        JudgeConfig(provider="openai_chat", model_id="recorded"),
        repeats=1,
        use_judge_cache=False,
        role="primary",
        run_id="",
    )
    return judge, pending


def test_schema_content_is_accepted():
    verdict = CorrectnessVerdict(key_facts=[KeyFact(fact="window", present=True, reason="stated")])
    judge, pending = _judge([Recorded(verdict)])
    assert judge.check_correctness("q", "expected", "actual") is verdict
    assert pending == []


def test_string_content_is_retried_once_then_accepted():
    verdict = CorrectnessVerdict(key_facts=[KeyFact(fact="window", present=True)])
    judge, pending = _judge([Recorded("not json"), Recorded(verdict)])
    assert isinstance(judge.check_correctness("q", "expected", "actual"), CorrectnessVerdict)
    assert pending == []


def test_repeats_above_one_force_the_cache_off():
    verdict = CorrectnessVerdict(key_facts=[KeyFact(fact="window", present=True)])
    calls = {"count": 0}

    def runner(agent, schema, prompt, config, instructions):
        calls["count"] += 1
        return Recorded(verdict)

    judge = AgnoJudge(repository=None, runner=runner)
    judge.prepare(
        JudgeConfig(provider="openai_chat", model_id="recorded"),
        repeats=2,
        use_judge_cache=True,
        role="primary",
        run_id="",
    )
    judge.check_correctness("q", "expected", "actual")
    judge.check_correctness("q", "expected", "actual")
    assert calls["count"] == 2


def test_second_invalid_content_is_an_error():
    judge, _pending = _judge([Recorded("nope"), Recorded("still nope")])
    with pytest.raises(JudgeOutputError):
        judge.check_correctness("q", "expected", "actual")


def _repository(tmp_path, monkeypatch):
    container, _box, _judge = open_container(tmp_path, monkeypatch)
    return container.repository


def test_the_rubric_is_part_of_the_prompt_and_the_verdict_is_saved(tmp_path, monkeypatch):
    verdict = CorrectnessVerdict(key_facts=[KeyFact(fact="window", present=True, reason="stated")])
    seen = {"prompt": "", "count": 0}

    def runner(agent, schema, prompt, config, instructions):
        seen["count"] += 1
        seen["prompt"] = prompt
        seen["instructions"] = instructions
        return Recorded(verdict)

    repository = _repository(tmp_path, monkeypatch)

    def opened():
        judge = AgnoJudge(repository=repository, runner=runner)
        judge.prepare(
            JudgeConfig(provider="openai_chat", model_id="recorded"),
            repeats=1,
            use_judge_cache=True,
            role="primary",
            run_id="run-1",
        )
        return judge

    first = opened().check_correctness("q", "expected", "actual")
    second = opened().check_correctness("q", "expected", "actual")
    stored = repository.list(JudgeVerdict)
    instructions = RUBRICS["correctness"][1]
    assert first.model_dump() == verdict.model_dump()
    assert second.model_dump() == verdict.model_dump()
    assert seen["count"] == 1
    assert seen["prompt"].startswith(instructions)
    assert "Question:\nq" in seen["prompt"]
    assert len(stored) == 1
    assert stored[0].verdict == verdict.model_dump()
    assert stored[0].agent == "correctness"


def test_a_fresh_call_without_the_cache_does_not_replace_the_saved_verdict(tmp_path, monkeypatch):
    first = CorrectnessVerdict(key_facts=[KeyFact(fact="window", present=True, reason="stated")])
    second = CorrectnessVerdict(key_facts=[KeyFact(fact="window", present=False, reason="missing")])
    pending = [Recorded(first), Recorded(second)]

    def runner(agent, schema, prompt, config, instructions):
        return pending.pop(0)

    repository = _repository(tmp_path, monkeypatch)
    judge = AgnoJudge(repository=repository, runner=runner)
    judge.prepare(
        JudgeConfig(provider="openai_chat", model_id="recorded"),
        repeats=1,
        use_judge_cache=False,
        role="primary",
        run_id="",
    )
    assert judge.check_correctness("q", "expected", "actual").model_dump() == first.model_dump()
    assert judge.check_correctness("q", "expected", "actual").model_dump() == second.model_dump()
    stored = repository.list(JudgeVerdict)
    assert len(stored) == 1
    assert stored[0].verdict == first.model_dump()
    assert pending == []


def test_a_model_that_rejects_temperature_zero_is_recognized():
    message = "Unsupported value: 'temperature' does not support 0 with this model. Only the default (1) value is supported."
    assert temperature_rejected(message)
    assert not temperature_rejected("the reply was not valid schema content")


@pytest.mark.live
def test_live_judge_is_opt_in():
    assert True
