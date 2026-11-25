from app.domain.errors import DomainError
from app.domain.models import CalibrationAgreement, CalibrationLabel, Dataset, MetricResult, Run, TestCase, new_id
from app.services.lookup import require


def cohen_kappa(pairs: list[tuple[bool, bool]]) -> float | None:
    count = len(pairs)
    if count == 0:
        return None
    both_true = sum(1 for human, judge in pairs if human and judge)
    human_only = sum(1 for human, judge in pairs if human and not judge)
    judge_only = sum(1 for human, judge in pairs if not human and judge)
    both_false = count - both_true - human_only - judge_only
    observed = (both_true + both_false) / count
    human_true = (both_true + human_only) / count
    judge_true = (both_true + judge_only) / count
    chance = human_true * judge_true + (1 - human_true) * (1 - judge_true)
    if chance == 1:
        return 1.0
    return (observed - chance) / (1 - chance)


class CalibrationService:
    def __init__(self, repository) -> None:
        self._repository = repository

    def save_labels(self, dataset_id: str, labels: list[dict]) -> list[CalibrationLabel]:
        require(self._repository, Dataset, dataset_id, "Dataset")
        stored: list[CalibrationLabel] = []
        for item in labels:
            case = require(self._repository, TestCase, item["test_case_id"], "Test case")
            if case.dataset_id != dataset_id:
                raise DomainError("validation_error", "Test case is not in this dataset")
            label = CalibrationLabel(
                id=new_id(),
                dataset_id=dataset_id,
                test_case_id=case.id,
                human_correct=bool(item["human_correct"]),
            )
            self._repository.add(label)
            stored.append(label)
        return stored

    def agreement(self, run_id: str) -> CalibrationAgreement:
        run = require(self._repository, Run, run_id, "Run")
        labels = self._repository.list(CalibrationLabel, dataset_id=run.dataset_id)
        metrics = [
            row
            for row in self._repository.list(MetricResult, run_id=run_id)
            if row.metric_id == "correctness" and row.judge_slot == "primary" and row.repeat_index == 0
        ]
        by_case = {row.test_case_id: row for row in metrics}
        pairs: list[tuple[bool, bool]] = []
        for label in labels:
            row = by_case.get(label.test_case_id)
            if row is None or row.status != "ok" or row.value is None:
                continue
            pairs.append((bool(label.human_correct), float(row.value) >= 0.8))
        kappa = cohen_kappa(pairs)
        count = len(pairs)
        trusted = 30 <= count <= 50
        if count == 0:
            message = "No hand labels yet."
            warn = False
        elif not trusted:
            message = "The labeled set should be 30 to 50 items."
            warn = True
        elif kappa is not None and kappa < 0.6:
            message = f"Cohen's kappa is {kappa:.2f}, below 0.6."
            warn = True
        else:
            message = f"Cohen's kappa is {0 if kappa is None else kappa:.2f}."
            warn = False
        return CalibrationAgreement(
            item_count=count,
            kappa=kappa,
            trusted=trusted,
            warn=warn,
            message=message,
        )
