from fastapi import APIRouter, Depends

from app.api.deps import get_project_service
from app.schemas.http import ProjectCreate, ProjectResponse
from app.services.project_service import ProjectService

router = APIRouter(prefix="/projects", tags=["projects"])


def _project(project) -> ProjectResponse:
    return ProjectResponse(id=project.id, name=project.name, created_at=project.created_at)


@router.post("", response_model=ProjectResponse)
def create_project(body: ProjectCreate, service: ProjectService = Depends(get_project_service)):
    return _project(service.create(body.name))


@router.get("", response_model=list[ProjectResponse])
def list_projects(service: ProjectService = Depends(get_project_service)):
    return [_project(project) for project in service.list_projects()]


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str, service: ProjectService = Depends(get_project_service)):
    return _project(service.get(project_id))
