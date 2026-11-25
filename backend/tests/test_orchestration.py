from app.domain.models import JudgeConfig, MetricResult, RunSpec
from tests.support import open_container, seed, start_run


def _csv_pair() -> str:
    return "\n".join(
        [
            "conversation_id,question,expected_answer,gold_passage",
            "c1,What is the refund window?,30 days,alpha beta gamma delta",
            "c1,Can I do that later?,yes,alpha beta gamma delta",
        ]
    )


def test_target_error_is_stored_and_the_run_succeeds(tmp_path, monkeypatch):
    container, box, _judge = open_container(tmp_path, monkeypatch)
    box.fail_questions.add("broken question")
    project, config, dataset = seed(
        container,
        "question,expected_answer,gold_passage\nbroken question,30 days,alpha beta gamma delta\n",
    )
    run = start_run(container, project, dataset, config)
    container.run_service.execute(run.id)
    stored = container.run_service.get(run.id)
    assert stored.status == "succeeded"
    traces = container.run_service.list_traces(run.id)
    assert traces[0].status == "error"
    assert traces[0].error == "forced target error"
    metrics = container.run_service.get_metrics(run.id)
    error_rate = metrics["summary"]["metrics"]["error_rate"]
    assert error_rate["value"] == 1
    assert error_rate["denominator"] == 1


def test_resume_skips_ok_traces_and_retries_errors(tmp_path, monkeypatch):
    container, box, _judge = open_container(tmp_path, monkeypatch)
    box.fail_questions.add("second")
    project, config, dataset = seed(
        container,
        "question,expected_answer,gold_passage\nfirst,30 days,alpha beta gamma delta\nsecond,30 days,alpha beta gamma delta\n",
    )
    run = start_run(container, project, dataset, config)
    container.run_service.execute(run.id)
    calls_after_first = len(box.calls)
    stored = container.run_service.get(run.id)
    stored.status = "failed"
    container.repository.add(stored)
    box.fail_questions.clear()
    resumed = container.run_service.resume(run.id)
    container.run_service.execute(resumed.id)
    questions = [call.question for call in box.calls]
    assert questions[:calls_after_first].count("first") == 1
    assert questions[calls_after_first:] == ["second"]
    traces = container.run_service.list_traces(run.id)
    assert {trace.question: trace.status for trace in traces} == {"first": "ok", "second": "ok"}


def test_reevaluate_does_not_call_the_adapter(tmp_path, monkeypatch):
    container, box, _judge = open_container(tmp_path, monkeypatch)
    project, config, dataset = seed(
        container,
        "question,expected_answer,gold_passage\nWhat is the refund window?,30 days,alpha beta gamma delta\n",
    )
    run = start_run(container, project, dataset, config)
    container.run_service.execute(run.id)
    assert len(box.calls) == 1
    replay = container.run_service.reevaluate(run.id, None, None, None)
    container.run_service.execute(replay.id)
    assert len(box.calls) == 1
    assert replay.replay_of_run_id == run.id
    assert container.run_service.get(replay.id).status == "succeeded"


def test_blank_judge_model_comes_from_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("EVAL_JUDGE_MODEL", "gpt-from-env")
    monkeypatch.setenv("EVAL_JUDGE_PROVIDER", "openai_responses")
    container, _box, _judge = open_container(tmp_path, monkeypatch)
    project, config, dataset = seed(container, "question,expected_answer\nWhat is the refund window?,30 days\n")
    run = container.run_service.start(
        RunSpec(
            project_id=project.id,
            dataset_id=dataset.id,
            system_config_version_id=config.id,
            judge=JudgeConfig(provider="openai_chat", model_id=""),
        ),
        None,
    )
    assert run.judge_config["model_id"] == "gpt-from-env"
    assert run.judge_config["provider"] == "openai_responses"


def test_follow_up_stores_counterfactual_and_first_turn_skips_history(tmp_path, monkeypatch):
    container, box, judge = open_container(tmp_path, monkeypatch)
    project, config, dataset = seed(container, _csv_pair())
    run = start_run(container, project, dataset, config)
    container.run_service.execute(run.id)
    traces = container.run_service.list_traces(run.id)
    kinds = {(trace.turn_index, trace.kind, trace.question) for trace in traces}
    assert (0, "primary", "What is the refund window?") in kinds
    assert (1, "standalone_counterfactual", "standalone question") in kinds
    assert all(call.history == [] for call in box.calls)
    primary_follow_up = next(call for call in box.calls if call.question == "Can I do that later?")
    standalone = next(call for call in box.calls if call.question == "standalone question")
    assert primary_follow_up.conversation_id == "c1"
    assert standalone.conversation_id is None
    assert judge.rewrite_calls == 1
    rows = container.run_service.get_metrics(run.id)["rows"]
    skipped = [row for row in rows if row.metric_id == "history_failure" and row.skip_reason == "not a follow-up"]
    scored = [row for row in rows if row.metric_id == "history_failure" and row.status == "ok"]
    assert len(skipped) == 1
    assert len(scored) == 1
    assert scored[0].details["primary_hit"] == 1
    assert scored[0].details["counterfactual_hit"] == 1


def test_estimate_matches_the_worked_example(tmp_path, monkeypatch):
    container, _box, _judge = open_container(tmp_path, monkeypatch)
    lines = ["conversation_id,question,expected_answer,gold_passage"]
    for index in range(20):
        lines.append(f"c{index},q{index}a,answer,gold passage")
        lines.append(f"c{index},q{index}b,answer,gold passage")
    for index in range(60):
        expected = "" if index < 20 else "answer"
        gold = "" if index < 30 else "gold passage"
        lines.append(f",single{index},{expected},{gold}")
    project, config, dataset = seed(container, "\n".join(lines), top_k=5)
    cases = container.dataset_service.list_cases(dataset.id)
    assert len(cases) == 100
    assert sum(1 for case in cases if case.turn_index > 0) == 20
    assert sum(1 for case in cases if case.expected_answer) == 80
    assert sum(1 for case in cases if case.gold_passage) == 70
    estimate = container.run_service.estimate(
        dataset.id,
        config.id,
        JudgeConfig(provider="openai_chat", model_id="judge-model"),
        1,
    )
    assert estimate.target_calls == 100
    assert estimate.counterfactual_calls == 20
    assert estimate.judge_calls == {
        "correctness": 80,
        "faithfulness": 100,
        "usefulness_worst_case": 350,
        "split_confirm_worst_case": 70,
        "rewrite": 20,
        "report_writer": 1,
    }


def test_idempotency_key_conflicts_on_a_different_body(tmp_path, monkeypatch):
    container, _box, _judge = open_container(tmp_path, monkeypatch)
    project, config, dataset = seed(
        container,
        "question,expected_answer,gold_passage\nWhat is the refund window?,30 days,alpha beta gamma delta\n",
    )
    from app.domain.errors import DomainError
    from app.domain.models import RunSpec

    spec = RunSpec(
        project_id=project.id,
        dataset_id=dataset.id,
        system_config_version_id=config.id,
        judge=JudgeConfig(provider="openai_chat", model_id="judge-model"),
    )
    first = container.run_service.start(spec, "key-1")
    again = container.run_service.start(spec, "key-1")
    assert again.id == first.id
    spec.repeats = 2
    try:
        container.run_service.start(spec, "key-1")
    except DomainError as exc:
        assert exc.code == "idempotency_conflict"
    else:
        raise AssertionError("expected idempotency conflict")


def test_repeats_disable_cache_and_record_variance(tmp_path, monkeypatch):
    container, _box, judge = open_container(tmp_path, monkeypatch)
    project, config, dataset = seed(
        container,
        "question,expected_answer,gold_passage\nWhat is the refund window?,30 days,alpha beta gamma delta\n",
    )
    run = start_run(container, project, dataset, config, repeats=2, use_judge_cache=True)
    container.run_service.execute(run.id)
    assert judge.prepared[1] == 2
    rows = container.repository.list(MetricResult, run_id=run.id)
    variance = [row for row in rows if row.metric_id == "judge_variance"]
    assert variance and variance[0].status == "ok"
