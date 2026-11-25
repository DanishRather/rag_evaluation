from fastapi import Request

from app.services.calibration_service import CalibrationService
from app.services.dataset_service import DatasetService
from app.services.diagnosis_service import DiagnosisService
from app.services.project_service import ProjectService
from app.services.report_service import ReportService
from app.services.run_service import RunService
from app.services.system_service import SystemService


def get_project_service(request: Request) -> ProjectService:
    return request.app.state.container.project_service


def get_system_service(request: Request) -> SystemService:
    return request.app.state.container.system_service


def get_dataset_service(request: Request) -> DatasetService:
    return request.app.state.container.dataset_service


def get_run_service(request: Request) -> RunService:
    return request.app.state.container.run_service


def get_diagnosis_service(request: Request) -> DiagnosisService:
    return request.app.state.container.diagnosis_service


def get_report_service(request: Request) -> ReportService:
    return request.app.state.container.report_service


def get_calibration_service(request: Request) -> CalibrationService:
    return request.app.state.container.calibration_service
