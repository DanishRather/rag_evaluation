from app.diagnosis.engine import first_match, load_rules, question_signals, rule_matches
from app.domain.models import Run, Trace, new_id, utc_now
from tests.support import metric, open_container, seed


def _signals(**overrides):
    base = {
        "correctness": "n/a",
        "faithfulness": "n/a",
        "gold_retrieved": "n/a",
        "split": "n/a",
        "standalone_works": "n/a",
        "correct": "n/a",
        "faithful": "n/a",
    }
    base.update(overrides)
    return base


def test_rules_match_in_file_order_and_na_ignores_a_signal():
    _version, rules = load_rules()
    history = _signals(gold_retrieved=False, standalone_works=True, correctness=0.1, correct=False)
    assert first_match(history, rules).id == "search_ignores_history"
    chunking = _signals(correctness=0.4, split=True, gold_retrieved=False, standalone_works=False)
    assert first_match(chunking, rules).id == "chunking_cut_the_answer"
    search = _signals(gold_retrieved=False, standalone_works="n/a")
    assert first_match(search, rules).id == "embedding_or_search_quality"
    ignored = _signals(faithfulness=0.2, faithful=False, gold_retrieved=True, split=False)
    assert first_match(ignored, rules).id == "llm_ignored_context"
    working = _signals(correctness=0.8, faithfulness=0.9, correct=True, faithful=True, gold_retrieved=True)
    assert first_match(working, rules).id == "working_as_intended"
    assert rule_matches({"correctness": {"max": 0.8}}, {"correctness": 0.8}) is False
    assert rule_matches({"correctness": {"min": 0.8}}, {"correctness": 0.8}) is True
    assert rule_matches({"correctness": "n/a", "gold_retrieved": False}, {"gold_retrieved": False}) is True


def test_five_questions_land_on_the_five_causes(tmp_path, monkeypatch):
    container, _box, _judge = open_container(tmp_path, monkeypatch)
    csv_text = "\n".join(
        [
            "question,expected_answer,gold_passage",
            "history question,30 days,gold",
            "chunk question,30 days,gold",
            "search question,30 days,gold",
            "llm question,30 days,gold",
            "working question,30 days,gold",
        ]
    )
    project, config, dataset = seed(container, csv_text)
    cases = container.dataset_service.list_cases(dataset.id)
    run = Run(
        id=new_id(),
        project_id=project.id,
        dataset_id=dataset.id,
        system_config_version_id=config.id,
        replay_of_run_id=None,
        judge_config={"provider": "openai_chat", "model_id": "judge-model", "temperature": 0},
        evaluator_ids=["correctness"],
        price_table=None,
        repeats=1,
        max_concurrency=1,
        status="succeeded",
        idempotency_key=None,
        request_hash="hash",
        use_judge_cache=False,
        target_timeout_s=60,
        target_max_attempts=1,
        capabilities={},
        created_at=utc_now(),
    )
    container.repository.add(run)
    rows = {
        cases[0].id: [
            metric(run.id, cases[0].id, "hit", 0),
            metric(run.id, cases[0].id, "history_failure", 1, counterfactual_hit=1, primary_hit=0),
            metric(run.id, cases[0].id, "correctness", 0.2),
        ],
        cases[1].id: [
            metric(run.id, cases[1].id, "correctness", 0.4),
            metric(run.id, cases[1].id, "chunk_split", 1),
            metric(run.id, cases[1].id, "hit", 1),
        ],
        cases[2].id: [
            metric(run.id, cases[2].id, "hit", 0),
            metric(run.id, cases[2].id, "correctness", 0.2),
        ],
        cases[3].id: [
            metric(run.id, cases[3].id, "faithfulness", 0.2),
            metric(run.id, cases[3].id, "hit", 1),
            metric(run.id, cases[3].id, "chunk_split", 0),
            metric(run.id, cases[3].id, "correctness", 0.5),
        ],
        cases[4].id: [
            metric(run.id, cases[4].id, "correctness", 1),
            metric(run.id, cases[4].id, "faithfulness", 1),
            metric(run.id, cases[4].id, "hit", 1),
        ],
    }
    for case in cases:
        container.repository.add(
            Trace(
                id=new_id(),
                run_id=run.id,
                test_case_id=case.id,
                conversation_id=None,
                turn_index=0,
                kind="primary",
                repeat_index=0,
                question=case.question,
                answer="answer",
                rewritten_query=None,
                error=None,
                latency_ms=1,
                prompt_tokens=1,
                completion_tokens=1,
                model="m",
                status="ok",
            )
        )
        for row in rows[case.id]:
            container.repository.add(row)
    outcome = container.diagnosis_service.diagnose(run.id)
    assert [item["cause"] for item in outcome.per_question] == [
        "Search ignores history",
        "Chunking cut the answer",
        "Embedding or search quality",
        "LLM ignored context",
        "Working as intended",
    ]
    assert [finding.cause for finding in outcome.findings] == [
        "Search ignores history",
        "Chunking cut the answer",
        "Embedding or search quality",
        "LLM ignored context",
        "Working as intended",
    ]
    history = outcome.findings[0]
    assert history.evidence["gold_retrieved"]["false"] == 1
    assert history.evidence["standalone_works"]["true"] == 1
    signals = question_signals(rows[cases[0].id], cases[0].id)
    assert signals["standalone_works"] is True
    assert signals["correctness"] == 0.2
