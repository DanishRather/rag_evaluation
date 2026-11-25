from fastapi import APIRouter, Depends
from fastapi.responses import Response

from app.api.deps import get_diagnosis_service, get_report_service
from app.schemas.http import FindingResponse
from app.services.diagnosis_service import DiagnosisService
from app.services.report_service import ReportService

router = APIRouter(tags=["reports"])


@router.get("/runs/compare")
def compare_runs(run_a: str, run_b: str, service: ReportService = Depends(get_report_service)):
    return service.compare(run_a, run_b)


@router.get("/runs/{run_id}/findings", response_model=list[FindingResponse])
def list_findings(run_id: str, service: DiagnosisService = Depends(get_diagnosis_service)):
    return [
        FindingResponse(
            id=finding.id,
            run_id=finding.run_id,
            rule_id=finding.rule_id,
            cause=finding.cause,
            severity=finding.severity,
            count=finding.count,
            example_question_ids=list(finding.example_question_ids),
            evidence=finding.evidence,
        )
        for finding in service.list_findings(run_id)
    ]


@router.get("/runs/{run_id}/report")
def get_report(run_id: str, service: ReportService = Depends(get_report_service)):
    return service.get_model(run_id)


@router.get("/runs/{run_id}/report.html")
def get_report_html(run_id: str, service: ReportService = Depends(get_report_service)):
    rendered = service.render(run_id, "html")
    return Response(content=rendered.body, media_type=rendered.media_type, headers={"Content-Disposition": f'attachment; filename="{rendered.filename}"'})


@router.get("/runs/{run_id}/report.pdf")
def get_report_pdf(run_id: str, service: ReportService = Depends(get_report_service)):
    rendered = service.render(run_id, "pdf")
    return Response(content=rendered.body, media_type=rendered.media_type, headers={"Content-Disposition": f'attachment; filename="{rendered.filename}"'})
