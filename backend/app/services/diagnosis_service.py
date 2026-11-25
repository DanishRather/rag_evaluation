from collections import Counter
from statistics import median

from app.diagnosis.engine import (
    aggregate_findings,
    first_match,
    load_rules,
    question_signals,
    setup_table,
)
from app.domain.models import (
    DiagnosisOutcome,
    Finding,
    MetricResult,
    Run,
    SystemConfig,
    SystemProfile,
    TestCase,
    Trace,
    new_id,
)
from app.evaluators.summary import summarize
from app.services.lookup import require


class DiagnosisService:
    def __init__(self, repository) -> None:
        self._repository = repository
        self._version, self._rules = load_rules()

    def cause_for(self, case: TestCase, metrics: list[MetricResult]) -> str | None:
        if not any(row.test_case_id == case.id and row.status == "ok" for row in metrics):
            return None
        rule = first_match(question_signals(metrics, case.id), self._rules)
        return None if rule is None else rule.cause

    def diagnose(self, run_id: str) -> DiagnosisOutcome:
        run = require(self._repository, Run, run_id, "Run")
        root_id = run.replay_of_run_id or run.id
        cases = self._repository.list(TestCase, dataset_id=run.dataset_id)
        metrics = self._repository.list(MetricResult, run_id=run_id)
        traces = self._repository.list(Trace, run_id=root_id)
        ok_cases = _ok_case_ids(traces)
        failed_cases = _failed_case_ids(traces)
        matched = []
        unclassified = 0
        per_question = []
        for case in cases:
            if case.id in failed_cases and case.id not in ok_cases:
                per_question.append({"test_case_id": case.id, "cause": None, "target_failure": True})
                continue
            if case.id not in ok_cases:
                continue
            signals = question_signals(metrics, case.id)
            rule = first_match(signals, self._rules)
            if rule is None:
                unclassified += 1
                per_question.append({"test_case_id": case.id, "cause": None, "target_failure": False})
                continue
            matched.append((case, rule, signals))
            per_question.append({"test_case_id": case.id, "cause": rule.cause, "target_failure": False})
        findings = aggregate_findings(matched, run_id, new_id)
        self._repository.remove(Finding, run_id=run_id)
        for finding in findings:
            self._repository.add(finding)
        return DiagnosisOutcome(
            findings=findings,
            unclassified=unclassified,
            target_failures=len(failed_cases - ok_cases),
            per_question=per_question,
        )

    def list_findings(self, run_id: str) -> list[Finding]:
        require(self._repository, Run, run_id, "Run")
        findings = self._repository.list(Finding, run_id=run_id)
        order = {rule.id: index for index, rule in enumerate(self._rules)}
        return sorted(findings, key=lambda finding: order.get(finding.rule_id, len(order)))

    def build_profile(self, run_id: str) -> SystemProfile:
        run = require(self._repository, Run, run_id, "Run")
        config = require(self._repository, SystemConfig, run.system_config_version_id, "System config")
        root_id = run.replay_of_run_id or run.id
        traces = [
            trace
            for trace in self._repository.list(Trace, run_id=root_id)
            if trace.status == "ok" and trace.kind == "primary"
        ]
        summary = summarize(self._repository.list(MetricResult, run_id=run_id))
        findings = self.list_findings(run_id)
        settings = config.profile_settings or {}
        counts = [len(trace.chunks) for trace in traces]
        models = [trace.model for trace in traces if trace.model]
        observed = Counter(models).most_common(1)[0][0] if models else None

        def metric_value(metric_id: str):
            row = summary["metrics"].get(metric_id) or {}
            if row.get("status") != "ok":
                return None
            return row.get("value")

        return SystemProfile(
            embedding_model=_text(settings.get("embedding_model")),
            top_k=_int(settings.get("top_k")),
            chunk_size_tokens=_int(settings.get("chunk_size_tokens")),
            chunk_overlap_tokens=_int(settings.get("chunk_overlap_tokens")),
            llm=_text(settings.get("llm")),
            prompts=settings.get("prompts"),
            mean_chunk_tokens=metric_value("avg_chunk_tokens"),
            neighbor_overlap=metric_value("neighbor_overlap"),
            median_chunk_count=None if not counts else float(median(counts)),
            observed_model=observed,
            split_answer_rate=metric_value("split_answer_rate"),
            hit=metric_value("hit"),
            history_failure_rate=metric_value("history_failure_rate"),
            finding_counts={finding.rule_id: finding.count for finding in findings},
        )

    def setup_rows(self, run_id: str):
        return setup_table(self.build_profile(run_id))


def _ok_case_ids(traces: list[Trace]) -> set[str]:
    return {trace.test_case_id for trace in traces if trace.kind == "primary" and trace.status == "ok"}


def _failed_case_ids(traces: list[Trace]) -> set[str]:
    return {trace.test_case_id for trace in traces if trace.kind == "primary" and trace.status == "error"}


def _text(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int(value):
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
