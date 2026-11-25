from app.domain.models import Project, new_id, utc_now
from app.services.lookup import require


class ProjectService:
    def __init__(self, repository) -> None:
        self._repository = repository

    def create(self, name: str) -> Project:
        cleaned = name.strip()
        if not cleaned:
            from app.domain.errors import DomainError

            raise DomainError("validation_error", "Project name is required")
        project = Project(id=new_id(), name=cleaned, created_at=utc_now())
        self._repository.add(project)
        return project

    def list_projects(self) -> list[Project]:
        return self._repository.list(Project)

    def get(self, project_id: str) -> Project:
        return require(self._repository, Project, project_id, "Project")
