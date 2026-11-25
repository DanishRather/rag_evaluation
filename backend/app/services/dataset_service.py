import csv
import io
import json
from pathlib import Path

from app.domain.errors import DomainError
from app.domain.models import CalibrationLabel, Dataset, DatasetView, Project, Run, TestCase, new_id, utc_now
from app.services.cleanup import purge_run
from app.services.lookup import require

_CANONICAL = ("question", "expected_answer", "gold_passage", "conversation_id")
_PARSERS = {}


def _text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def parse_csv(payload: bytes) -> tuple[list[str], list[dict]]:
    reader = csv.DictReader(io.StringIO(payload.decode("utf-8-sig")))
    if not reader.fieldnames:
        raise DomainError("validation_error", "CSV has no header row")
    headers = [name.strip() for name in reader.fieldnames]
    rows = []
    for raw in reader:
        row = {}
        for header, original in zip(headers, reader.fieldnames, strict=False):
            if header:
                row[header] = _text(raw.get(original))
        if any(row.values()):
            rows.append(row)
    return [header for header in headers if header], rows


def parse_json(payload: bytes) -> tuple[list[str], list[dict]]:
    try:
        data = json.loads(payload.decode("utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise DomainError("validation_error", "JSON file is not an array of objects") from exc
    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise DomainError("validation_error", "JSON file must be an array of objects")
    headers: list[str] = []
    for item in data:
        for key in item:
            name = str(key).strip()
            if name and name not in headers:
                headers.append(name)
    rows = [{header: _text(item.get(header)) for header in headers} for item in data]
    return headers, [row for row in rows if any(row.values())]


def parse_xlsx(payload: bytes) -> tuple[list[str], list[dict]]:
    from openpyxl import load_workbook

    workbook = load_workbook(io.BytesIO(payload), read_only=True, data_only=True)
    sheet = workbook.worksheets[0]
    iterator = sheet.iter_rows(values_only=True)
    try:
        header_row = next(iterator)
    except StopIteration as exc:
        raise DomainError("validation_error", "Spreadsheet has no header row") from exc
    headers = ["" if cell is None else str(cell).strip() for cell in header_row]
    while headers and not headers[-1]:
        headers.pop()
    if not any(headers):
        raise DomainError("validation_error", "Spreadsheet has no header row")
    rows = []
    for values in iterator:
        if values is None:
            continue
        row = {}
        empty = True
        for index, header in enumerate(headers):
            if not header:
                continue
            cell = values[index] if index < len(values) else None
            text = _text(cell)
            row[header] = text
            if text:
                empty = False
        if not empty:
            rows.append(row)
    workbook.close()
    return [header for header in headers if header], rows


_PARSERS[".csv"] = parse_csv
_PARSERS[".json"] = parse_json
_PARSERS[".xlsx"] = parse_xlsx


class DatasetService:
    def __init__(self, repository) -> None:
        self._repository = repository

    def import_file(self, project_id: str, filename: str, payload: bytes) -> DatasetView:
        require(self._repository, Project, project_id, "Project")
        if not payload:
            raise DomainError("validation_error", "Upload a CSV, JSON, or XLSX file")
        suffix = Path(filename or "").suffix.lower()
        try:
            parser = _PARSERS[suffix]
        except KeyError as exc:
            raise DomainError("validation_error", "Upload a CSV, JSON, or XLSX file") from exc
        headers, rows = parser(payload)
        column_map = {name: name for name in _CANONICAL if name in headers}
        dataset = Dataset(
            id=new_id(),
            project_id=project_id,
            name=Path(filename).stem or "dataset",
            source_filename=filename or "upload",
            column_map=column_map if "question" in column_map else {},
            headers=headers,
            raw_rows=rows,
            created_at=utc_now(),
        )
        self._repository.add(dataset)
        if "question" in column_map:
            try:
                self._store_cases(dataset, column_map)
            except DomainError:
                self._repository.remove(Dataset, id=dataset.id)
                raise
        return self._view(dataset)

    def apply_mapping(self, dataset_id: str, column_map: dict) -> DatasetView:
        dataset = require(self._repository, Dataset, dataset_id, "Dataset")
        if self._repository.list(Run, dataset_id=dataset_id):
            raise DomainError("validation_error", "Dataset already has runs")
        mapping = {key: value for key, value in column_map.items() if value}
        question_header = mapping.get("question")
        if not question_header or question_header not in dataset.headers:
            raise DomainError("validation_error", "Map a file column to question")
        for key, header in mapping.items():
            if key not in _CANONICAL:
                raise DomainError("validation_error", "Unknown dataset column", {"column": key})
            if header not in dataset.headers:
                raise DomainError("validation_error", "Mapped column is not in the file", {"column": header})
        planned = self._plan_cases(dataset, mapping)
        dataset.column_map = mapping
        self._repository.add(dataset)
        self._repository.remove(TestCase, dataset_id=dataset_id)
        for case in planned:
            self._repository.add(case)
        return self._view(dataset)

    def get(self, dataset_id: str) -> DatasetView:
        dataset = require(self._repository, Dataset, dataset_id, "Dataset")
        return self._view(dataset)

    def list_datasets(self, project_id: str) -> list[DatasetView]:
        require(self._repository, Project, project_id, "Project")
        datasets = self._repository.list(Dataset, project_id=project_id)
        return [self._view(dataset) for dataset in reversed(datasets)]

    def list_cases(self, dataset_id: str) -> list[TestCase]:
        require(self._repository, Dataset, dataset_id, "Dataset")
        return self._repository.list(TestCase, dataset_id=dataset_id)

    def delete(self, dataset_id: str) -> None:
        require(self._repository, Dataset, dataset_id, "Dataset")
        runs = self._repository.list(Run, dataset_id=dataset_id)
        if any(run.status not in {"succeeded", "failed", "cancelled"} for run in runs):
            raise DomainError(
                "validation_error",
                "Cancel the run that uses this file and wait until it stops before deleting it.",
            )
        for run in runs:
            if run.replay_of_run_id:
                purge_run(self._repository, run.id)
        for run in runs:
            if not run.replay_of_run_id:
                purge_run(self._repository, run.id)
        self._repository.remove(CalibrationLabel, dataset_id=dataset_id)
        self._repository.remove(TestCase, dataset_id=dataset_id)
        self._repository.remove(Dataset, id=dataset_id)

    def _store_cases(self, dataset: Dataset, column_map: dict) -> None:
        for case in self._plan_cases(dataset, column_map):
            self._repository.add(case)

    def _plan_cases(self, dataset: Dataset, column_map: dict) -> list[TestCase]:
        question_header = column_map["question"]
        cases: list[TestCase] = []
        counts: dict[str, int] = {}
        for index, row in enumerate(dataset.raw_rows):
            question = _text(row.get(question_header))
            if not question:
                raise DomainError("validation_error", "Question is blank", {"row": index + 1})
            conversation = _optional(row, column_map.get("conversation_id"))
            turn_index = 0
            if conversation:
                turn_index = counts.get(conversation, 0)
                counts[conversation] = turn_index + 1
            cases.append(
                TestCase(
                    id=new_id(),
                    dataset_id=dataset.id,
                    source_row=index,
                    conversation_id=conversation,
                    turn_index=turn_index,
                    question=question,
                    expected_answer=_optional(row, column_map.get("expected_answer")),
                    gold_passage=_optional(row, column_map.get("gold_passage")),
                )
            )
        return cases

    def _view(self, dataset: Dataset) -> DatasetView:
        cases = self._repository.list(TestCase, dataset_id=dataset.id)
        return DatasetView(
            dataset=dataset,
            preview=list(dataset.raw_rows[:5]),
            case_count=len(cases),
            needs_mapping="question" not in (dataset.column_map or {}),
        )


def _optional(row: dict, header: str | None) -> str | None:
    if not header:
        return None
    text = _text(row.get(header))
    return text or None
