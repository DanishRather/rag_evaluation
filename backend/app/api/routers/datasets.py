from fastapi import APIRouter, Depends, File, UploadFile

from app.api.deps import get_dataset_service
from app.schemas.http import ColumnMapRequest, DatasetResponse, TestCaseResponse
from app.services.dataset_service import DatasetService

router = APIRouter(tags=["datasets"])


def _dataset(view) -> DatasetResponse:
    dataset = view.dataset
    return DatasetResponse(
        id=dataset.id,
        project_id=dataset.project_id,
        name=dataset.name,
        source_filename=dataset.source_filename,
        headers=list(dataset.headers),
        column_map=dict(dataset.column_map),
        preview=list(view.preview),
        case_count=view.case_count,
        needs_mapping=view.needs_mapping,
    )


@router.post("/projects/{project_id}/datasets", response_model=DatasetResponse)
async def create_dataset(
    project_id: str,
    file: UploadFile = File(...),
    service: DatasetService = Depends(get_dataset_service),
):
    payload = await file.read()
    return _dataset(service.import_file(project_id, file.filename or "upload", payload))


@router.get("/projects/{project_id}/datasets", response_model=list[DatasetResponse])
def list_datasets(project_id: str, service: DatasetService = Depends(get_dataset_service)):
    return [_dataset(view) for view in service.list_datasets(project_id)]


@router.put("/datasets/{dataset_id}/mapping", response_model=DatasetResponse)
def map_columns(dataset_id: str, body: ColumnMapRequest, service: DatasetService = Depends(get_dataset_service)):
    mapping = {"question": body.question}
    if body.expected_answer:
        mapping["expected_answer"] = body.expected_answer
    if body.gold_passage:
        mapping["gold_passage"] = body.gold_passage
    if body.conversation_id:
        mapping["conversation_id"] = body.conversation_id
    return _dataset(service.apply_mapping(dataset_id, mapping))


@router.delete("/datasets/{dataset_id}", status_code=204)
def delete_dataset(dataset_id: str, service: DatasetService = Depends(get_dataset_service)):
    service.delete(dataset_id)


@router.get("/datasets/{dataset_id}", response_model=DatasetResponse)
def get_dataset(dataset_id: str, service: DatasetService = Depends(get_dataset_service)):
    return _dataset(service.get(dataset_id))


@router.get("/datasets/{dataset_id}/cases", response_model=list[TestCaseResponse])
def list_cases(dataset_id: str, service: DatasetService = Depends(get_dataset_service)):
    return [
        TestCaseResponse(
            id=case.id,
            dataset_id=case.dataset_id,
            source_row=case.source_row,
            conversation_id=case.conversation_id,
            turn_index=case.turn_index,
            question=case.question,
            expected_answer=case.expected_answer,
            gold_passage=case.gold_passage,
        )
        for case in service.list_cases(dataset_id)
    ]
