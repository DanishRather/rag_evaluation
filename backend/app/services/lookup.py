from app.domain.errors import DomainError


def require(repository, kind: type, entity_id: str, label: str):
    entity = repository.get(kind, entity_id)
    if entity is None:
        raise DomainError("not_found", f"{label} not found")
    return entity
