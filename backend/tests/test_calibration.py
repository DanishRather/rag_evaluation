from app.domain.models import MetricResult, Run, new_id, utc_now
from app.services.calibration_service import cohen_kappa
from tests.support import open_container, seed


def test_kappa_warns_below_point_six_on_a_trusted_set(tmp_path, monkeypatch):
    container, _box, _judge = open_container(tmp_path, monkeypatch)
    lines = ["question,expected_answer"]
    lines.extend(f"Question {index}?,answer" for index in range(30))
    project, config, dataset = seed(container, "\n".join(lines))
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
    labels = []
    for index, case in enumerate(cases):
        human = index < 20
        labels.append({"test_case_id": case.id, "human_correct": human})
        container.repository.add(
            MetricResult(
                id=new_id(),
                run_id=run.id,
                test_case_id=case.id,
                metric_id="correctness",
                value=0.0,
                status="ok",
                skip_reason=None,
                details={"numerator": 0, "denominator": 1},
                rubric_version=1,
                judge_model="judge-model",
                temperature=0,
                judge_role="correctness",
                prompt_hash="hash",
                repeat_index=0,
                judge_slot="primary",
            )
        )
    container.calibration_service.save_labels(dataset.id, labels)
    agreement = container.calibration_service.agreement(run.id)
    assert agreement.item_count == 30
    assert agreement.trusted is True
    assert agreement.warn is True
    assert agreement.kappa is not None and agreement.kappa < 0.6
    assert "below 0.6" in agreement.message
    assert cohen_kappa([(True, False)] * 20 + [(False, False)] * 10) == agreement.kappa
