from app.domain.models import (
    AdapterBuild,
    Capabilities,
    Chunk,
    JudgeConfig,
    MetricResult,
    QueryRequest,
    RunSpec,
    Trace,
    new_id,
)
from app.main import create_container
from tests.fakes import FakeJudge, ScriptAdapter

GOLD = "alpha beta gamma delta"


class AdapterBox:
    def __init__(self) -> None:
        self.adapters: list[ScriptAdapter] = []
        self.fail_questions: set[str] = set()

    def factory(self, build: AdapterBuild) -> ScriptAdapter:
        box = self

        def handler(request: QueryRequest) -> Trace:
            if request.question in box.fail_questions:
                return Trace(
                    id=new_id(),
                    run_id="",
                    test_case_id=request.test_case_id,
                    conversation_id=request.conversation_id,
                    turn_index=request.turn_index,
                    kind="primary",
                    repeat_index=0,
                    question=request.question,
                    answer=None,
                    rewritten_query=None,
                    error="forced target error",
                    latency_ms=None,
                    prompt_tokens=None,
                    completion_tokens=None,
                    model=None,
                    status="error",
                    chunks=[],
                )
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
                rewritten_query="rewritten",
                error=None,
                latency_ms=12,
                prompt_tokens=8,
                completion_tokens=3,
                model="target-model",
                status="ok",
                chunks=[Chunk("c1", 1, GOLD, 0.9, "policy.md", 1, 4)],
            )

        adapter = ScriptAdapter(handler, Capabilities(True, True, True, True))
        self.adapters.append(adapter)
        return adapter

    @property
    def calls(self) -> list[QueryRequest]:
        return [call for adapter in self.adapters for call in adapter.calls]


def open_container(tmp_path, monkeypatch, box: AdapterBox | None = None):
    monkeypatch.setenv("EVAL_SECRET_KEY", "test-secret-key")
    monkeypatch.delenv("EVAL_ALLOW_PYTHON_ADAPTERS", raising=False)
    holder = box or AdapterBox()
    judge = FakeJudge()
    container = create_container(
        f"sqlite:///{tmp_path / 'eval.db'}",
        judge=judge,
        secondary_judge=FakeJudge(),
        adapter_factories={"fake": holder.factory},
    )
    return container, holder, judge


def seed(container, csv_text: str, *, top_k: int = 5):
    project = container.project_service.create("Support")
    system = container.system_service.create_system(project.id, "bot")
    config = container.system_service.add_config(
        system.id,
        "fake",
        {"url": "https://rag.example/query"},
        {"top_k": top_k, "embedding_model": "embed", "llm": "answer-model"},
        None,
    )
    view = container.dataset_service.import_file(project.id, "cases.csv", csv_text.encode())
    return project, config, view.dataset


def start_run(container, project, dataset, config, **overrides):
    spec = RunSpec(
        project_id=project.id,
        dataset_id=dataset.id,
        system_config_version_id=config.id,
        judge=JudgeConfig(provider="openai_chat", model_id="judge-model"),
        target_max_attempts=1,
        max_concurrency=1,
    )
    for key, value in overrides.items():
        setattr(spec, key, value)
    return container.run_service.start(spec, None)


def metric(run_id: str, case_id: str, metric_id: str, value: float | None, **details) -> MetricResult:
    status = "ok" if value is not None else "skipped"
    return MetricResult(
        id=new_id(),
        run_id=run_id,
        test_case_id=case_id,
        metric_id=metric_id,
        value=value,
        status=status,
        skip_reason=None if status == "ok" else "skipped",
        details=details or ({"numerator": value, "denominator": 1} if value is not None else {}),
        rubric_version=1,
        judge_model="judge-model",
        temperature=0,
        judge_role=metric_id,
        prompt_hash="hash",
        repeat_index=0,
        judge_slot="primary",
    )
