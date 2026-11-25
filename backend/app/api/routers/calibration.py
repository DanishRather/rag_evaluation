from fastapi import APIRouter, Depends

from app.api.deps import get_calibration_service
from app.schemas.http import CalibrationAgreementResponse, CalibrationLabelCreate
from app.services.calibration_service import CalibrationService

router = APIRouter(tags=["calibration"])


@router.put("/datasets/{dataset_id}/calibration-labels")
def save_labels(
    dataset_id: str,
    body: CalibrationLabelCreate,
    service: CalibrationService = Depends(get_calibration_service),
):
    labels = service.save_labels(dataset_id, body.labels)
    return [
        {"id": label.id, "dataset_id": label.dataset_id, "test_case_id": label.test_case_id, "human_correct": label.human_correct}
        for label in labels
    ]


@router.get("/runs/{run_id}/calibration", response_model=CalibrationAgreementResponse)
def calibration(run_id: str, service: CalibrationService = Depends(get_calibration_service)):
    agreement = service.agreement(run_id)
    return CalibrationAgreementResponse(
        item_count=agreement.item_count,
        kappa=agreement.kappa,
        trusted=agreement.trusted,
        warn=agreement.warn,
        message=agreement.message,
    )
