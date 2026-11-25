from app.diagnosis.engine import load_rules, setup_table
from app.domain.errors import DomainError, JudgeOutputError
from app.domain.models import Finding, MetricResult, Report, Run, SystemConfig, new_id
from app.domain.verdicts import ReportProse
from app.evaluators.summary import summarize
from app.services.lookup import require


class ReportService:
    def __init__(self, repository, judge, renderers: dict, diagnosis, calibration) -> None:
        self._repository = repository
        self._judge = judge
        self._renderers = renderers
        self._diagnosis = diagnosis
        self._calibration = calibration

    def write(self, run_id: str) -> Report:
        run = require(self._repository, Run, run_id, "Run")
        outcome = self._diagnosis.diagnose(run_id)
        try:
            prose = self._judge.write_report(outcome.findings)
        except JudgeOutputError:
            prose = ReportProse(summary="", finding_notes=[])
        known = {finding.id for finding in outcome.findings}
        notes = {
            note.finding_id: note.prose
            for note in prose.finding_notes
            if note.finding_id in known
        }
        profile = self._diagnosis.build_profile(run_id)
        rows = [
            {"id": row.id, "setting": row.setting, "current": row.current, "try": row.try_this, "why": row.why}
            for row in setup_table(profile)
        ]
        metrics = self._repository.list(MetricResult, run_id=run_id)
        summary = summarize(metrics)
        rubric_versions = {
            row.judge_role: row.rubric_version
            for row in metrics
            if row.judge_role and row.rubric_version is not None
        }
        _version, rules = load_rules()
        causes = {rule.id: 0 for rule in rules}
        for finding in outcome.findings:
            causes[finding.rule_id] = finding.count
        causes["unclassified"] = outcome.unclassified
        causes["target_failures"] = outcome.target_failures
        config = self._repository.get(SystemConfig, run.system_config_version_id)
        agreement = self._calibration.agreement(run_id)
        model = {
            "header": _header(run, config, rubric_versions),
            "score_summary": [
                {
                    "id": metric_id,
                    "value": row.get("value"),
                    "numerator": row.get("numerator"),
                    "denominator": row.get("denominator"),
                    "status": row.get("status"),
                    "skip_reason": (row.get("details") or {}).get("skip_reason"),
                }
                for metric_id, row in summary["metrics"].items()
            ],
            "skipped": summary["skipped"],
            "failure_causes": causes,
            "findings": [
                {
                    "id": finding.id,
                    "rule_id": finding.rule_id,
                    "cause": finding.cause,
                    "severity": finding.severity,
                    "count": finding.count,
                    "example_question_ids": finding.example_question_ids,
                    "evidence": finding.evidence,
                    "prose": notes.get(finding.id, ""),
                }
                for finding in outcome.findings
            ],
            "setup_table": rows,
            "compare": None,
            "calibration": {
                "item_count": agreement.item_count,
                "kappa": agreement.kappa if agreement.trusted else None,
                "trusted": agreement.trusted,
                "warn": agreement.warn,
                "message": agreement.message,
            },
            "summary_text": prose.summary,
        }
        self._repository.remove(Report, run_id=run_id)
        report = Report(id=new_id(), run_id=run_id, model=model)
        self._repository.add(report)
        return report

    def get_model(self, run_id: str) -> dict:
        report = self._require_report(run_id)
        return report.model

    def render(self, run_id: str, kind: str):
        report = self._require_report(run_id)
        try:
            renderer = self._renderers[kind]
        except KeyError as exc:
            raise DomainError("validation_error", "Unknown report format") from exc
        return renderer.render(report)

    def compare(self, run_a_id: str, run_b_id: str) -> dict:
        first = require(self._repository, Run, run_a_id, "Run")
        second = require(self._repository, Run, run_b_id, "Run")
        if first.dataset_id != second.dataset_id:
            raise DomainError("dataset_mismatch", "Runs belong to different datasets")
        if not self._repository.list(Report, run_id=first.id) or not self._repository.list(Report, run_id=second.id):
            raise DomainError("not_ready", "Both runs need a report before they can be compared")
        left = summarize(self._repository.list(MetricResult, run_id=first.id))
        right = summarize(self._repository.list(MetricResult, run_id=second.id))
        metric_ids = sorted(set(left["metrics"]) | set(right["metrics"]))
        metrics = []
        for metric_id in metric_ids:
            value_a = (left["metrics"].get(metric_id) or {}).get("value")
            value_b = (right["metrics"].get(metric_id) or {}).get("value")
            delta = None if value_a is None or value_b is None else value_b - value_a
            metrics.append({"metric_id": metric_id, "a": value_a, "b": value_b, "delta": delta})
        findings_a = {row.rule_id: row.count for row in self._repository.list(Finding, run_id=first.id)}
        findings_b = {row.rule_id: row.count for row in self._repository.list(Finding, run_id=second.id)}
        return {
            "run_a": first.id,
            "run_b": second.id,
            "metrics": metrics,
            "resolved": [
                {"rule_id": rule_id, "count_a": findings_a[rule_id], "count_b": 0}
                for rule_id in findings_a
                if rule_id not in findings_b
            ],
            "added": [
                {"rule_id": rule_id, "count_a": 0, "count_b": findings_b[rule_id]}
                for rule_id in findings_b
                if rule_id not in findings_a
            ],
            "still_present": [
                {"rule_id": rule_id, "count_a": findings_a[rule_id], "count_b": findings_b[rule_id]}
                for rule_id in findings_a
                if rule_id in findings_b
            ],
        }

    def _require_report(self, run_id: str) -> Report:
        require(self._repository, Run, run_id, "Run")
        rows = self._repository.list(Report, run_id=run_id)
        if not rows:
            raise DomainError("not_ready", "Report is not ready")
        return rows[0]


def _header(run: Run, config: SystemConfig | None, rubric_versions: dict) -> dict:
    judge = run.judge_config or {}
    return {
        "run_id": run.id,
        "dataset_id": run.dataset_id,
        "system_config_version": None if config is None else config.version,
        "judge_provider": judge.get("provider"),
        "model_id": judge.get("model_id"),
        "rubric_versions": rubric_versions,
        "temperature": 0,
        "repeats": run.repeats,
    }
