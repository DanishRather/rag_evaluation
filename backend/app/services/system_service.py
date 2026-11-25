import json
import re

from app.domain.errors import DomainError
from app.domain.models import (
    AdapterBuild,
    ProbeResult,
    Project,
    QueryRequest,
    Run,
    Secret,
    System,
    SystemConfig,
    new_id,
    utc_now,
)
from app.services.cleanup import purge_run
from app.services.lookup import require

_QUESTION = re.compile(r"\{\{[^}]*\bquestion\b[^}]*\}\}")


class SystemService:
    def __init__(self, repository, adapter_factories: dict, seal) -> None:
        self._repository = repository
        self._adapters = adapter_factories
        self._seal = seal

    def create_system(self, project_id: str, name: str) -> System:
        require(self._repository, Project, project_id, "Project")
        cleaned = name.strip()
        if not cleaned:
            raise DomainError("validation_error", "System name is required")
        system = System(id=new_id(), project_id=project_id, name=cleaned, created_at=utc_now())
        self._repository.add(system)
        return system

    def add_config(
        self,
        system_id: str,
        adapter_type: str,
        adapter_settings: dict,
        profile_settings: dict,
        auth_secret: str | None,
    ) -> SystemConfig:
        system = require(self._repository, System, system_id, "System")
        require(self._repository, Project, system.project_id, "Project")
        if adapter_type not in self._adapters:
            raise DomainError("validation_error", "Unknown adapter type", {"adapter_type": adapter_type})
        settings = dict(adapter_settings or {})
        secret = self._store_secret(system.project_id, auth_secret, settings)
        self._build(adapter_type, settings, secret, timeout_s=float(settings.get("timeout_s") or 60))
        versions = self._repository.list(SystemConfig, system_id=system_id)
        version = 1 if not versions else max(item.version for item in versions) + 1
        config = SystemConfig(
            id=new_id(),
            system_id=system_id,
            version=version,
            adapter_type=adapter_type,
            adapter_settings=settings,
            profile_settings=dict(profile_settings or {}),
            secret_id=None if secret is None else secret.id,
        )
        self._repository.add(config)
        return config

    def list_configs(self, system_id: str) -> list[SystemConfig]:
        require(self._repository, System, system_id, "System")
        return self._repository.list(SystemConfig, system_id=system_id)

    def list_systems(self, project_id: str) -> list[System]:
        require(self._repository, Project, project_id, "Project")
        return self._repository.list(System, project_id=project_id)

    def list_connections(self) -> list[dict]:
        """Latest config of every system, newest system first."""
        projects = {project.id: project for project in self._repository.list(Project)}
        rows: list[dict] = []
        for system in self._repository.list(System):
            configs = self._repository.list(SystemConfig, system_id=system.id)
            project = projects.get(system.project_id)
            if not configs or project is None:
                continue
            rows.append({"project": project, "system": system, "config": configs[-1]})
        rows.sort(key=lambda row: row["system"].created_at, reverse=True)
        return rows

    def delete_system(self, system_id: str) -> None:
        require(self._repository, System, system_id, "System")
        configs = self._repository.list(SystemConfig, system_id=system_id)
        config_ids = {config.id for config in configs}
        runs = [run for run in self._repository.list(Run) if run.system_config_version_id in config_ids]
        if any(run.status in {"queued", "running", "cancel_requested"} for run in runs):
            raise DomainError(
                "validation_error",
                "Cancel this connection's run and wait until it stops before deleting it.",
            )
        if any(run.status == "succeeded" for run in runs):
            raise DomainError(
                "validation_error",
                "This connection has a finished run. It stays so those results keep their endpoint.",
            )
        for run in runs:
            purge_run(self._repository, run.id)
        for config in configs:
            self._repository.remove(SystemConfig, id=config.id)
        self._repository.remove(System, id=system_id)

    def delete_broken(self) -> int:
        removed = 0
        for row in self.list_connections():
            config = row["config"]
            template = str((config.adapter_settings or {}).get("request_template") or "")
            if config.adapter_type != "http" or not template or _QUESTION.search(template):
                continue
            self.delete_system(row["system"].id)
            removed += 1
        return removed

    def probe(self, config_id: str, question: str = "ping") -> ProbeResult:
        text = question.strip()
        if not text:
            raise DomainError("validation_error", "Enter a query to test")
        config = require(self._repository, SystemConfig, config_id, "System config")
        secret = None if config.secret_id is None else require(self._repository, Secret, config.secret_id, "Secret")
        adapter = self._build(config.adapter_type, config.adapter_settings, secret, timeout_s=180)
        trace = adapter.run_query(
            QueryRequest(question=text, history=[], test_case_id="", conversation_id=None, turn_index=0)
        )
        return ProbeResult(
            capabilities=adapter.capabilities(),
            observed={
                "chunks": bool(trace.chunks),
                "scores": any(chunk.score is not None for chunk in trace.chunks),
                "rewritten_query": bool(trace.rewritten_query),
                "token_usage": trace.prompt_tokens is not None or trace.completion_tokens is not None,
            },
            error=trace.error,
            answer=trace.answer,
        )

    def _store_secret(self, project_id: str, auth_secret: str | None, settings: dict) -> Secret | None:
        if auth_secret is None or auth_secret == "":
            return None
        if self._seal is None:
            raise DomainError("validation_error", "EVAL_SECRET_KEY is required to store a secret")
        encoded = json.dumps(settings)
        if auth_secret in encoded:
            raise DomainError("validation_error", "Do not place the secret value in adapter settings")
        ciphertext, nonce = self._seal(auth_secret)
        secret = Secret(id=new_id(), project_id=project_id, ciphertext=ciphertext, nonce=nonce)
        self._repository.add(secret)
        return secret

    def _build(self, adapter_type: str, settings: dict, secret: Secret | None, timeout_s: float):
        try:
            factory = self._adapters[adapter_type]
        except KeyError as exc:
            raise DomainError("validation_error", "Unknown adapter type") from exc
        return factory(AdapterBuild(settings=settings, secret=secret, timeout_s=timeout_s))
