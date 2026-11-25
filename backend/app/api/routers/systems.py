from fastapi import APIRouter, Body, Depends

from app.api.deps import get_system_service
from app.schemas.http import (
    ConnectionResponse,
    ProbeRequest,
    ProbeResponse,
    SystemConfigCreate,
    SystemConfigResponse,
    SystemCreate,
    SystemResponse,
)
from app.services.system_service import SystemService

router = APIRouter(tags=["systems"])


def _system(system) -> SystemResponse:
    return SystemResponse(id=system.id, project_id=system.project_id, name=system.name, created_at=system.created_at)


def _config(config) -> SystemConfigResponse:
    return SystemConfigResponse(
        id=config.id,
        system_id=config.system_id,
        version=config.version,
        adapter_type=config.adapter_type,
        adapter_settings=config.adapter_settings,
        profile_settings=config.profile_settings,
        secret_id=config.secret_id,
    )


@router.post("/projects/{project_id}/systems", response_model=SystemResponse)
def create_system(project_id: str, body: SystemCreate, service: SystemService = Depends(get_system_service)):
    return _system(service.create_system(project_id, body.name))


@router.get("/projects/{project_id}/systems", response_model=list[SystemResponse])
def list_systems(project_id: str, service: SystemService = Depends(get_system_service)):
    return [_system(system) for system in service.list_systems(project_id)]


@router.delete("/connections/broken")
def delete_broken_connections(service: SystemService = Depends(get_system_service)):
    return {"deleted": service.delete_broken()}


@router.delete("/systems/{system_id}", status_code=204)
def delete_system(system_id: str, service: SystemService = Depends(get_system_service)):
    service.delete_system(system_id)


@router.get("/connections", response_model=list[ConnectionResponse])
def list_connections(service: SystemService = Depends(get_system_service)):
    return [
        ConnectionResponse(
            project_id=row["project"].id,
            project_name=row["project"].name,
            system_id=row["system"].id,
            system_name=row["system"].name,
            created_at=row["system"].created_at,
            config=_config(row["config"]),
        )
        for row in service.list_connections()
    ]


@router.post("/systems/{system_id}/configs", response_model=SystemConfigResponse)
def create_config(system_id: str, body: SystemConfigCreate, service: SystemService = Depends(get_system_service)):
    return _config(
        service.add_config(
            system_id,
            body.adapter_type,
            body.adapter_settings,
            body.profile_settings,
            body.auth_secret,
        )
    )


@router.get("/systems/{system_id}/configs", response_model=list[SystemConfigResponse])
def list_configs(system_id: str, service: SystemService = Depends(get_system_service)):
    return [_config(config) for config in service.list_configs(system_id)]


@router.post("/system-configs/{config_id}/probe", response_model=ProbeResponse)
def probe(
    config_id: str,
    body: ProbeRequest | None = Body(default=None),
    service: SystemService = Depends(get_system_service),
):
    result = service.probe(config_id, "ping" if body is None else body.question)
    return ProbeResponse(
        capabilities=result.capabilities.to_dict(),
        observed=result.observed,
        error=result.error,
        answer=result.answer,
    )
