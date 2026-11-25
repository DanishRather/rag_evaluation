"""User-supplied Python object adapter. Registered only when the env flag is on."""

from __future__ import annotations

import importlib
import os

from app.domain.errors import DomainError
from app.domain.models import AdapterBuild, Capabilities, QueryRequest, Trace
from app.infrastructure.adapters.mapper import error_trace
from app.security.redact import redact


class PythonObjectAdapter:
    def __init__(self, build: AdapterBuild) -> None:
        path = str(build.settings.get("import_path") or "")
        if ":" not in path:
            raise DomainError("validation_error", "Python adapter import path must look like package.module:Class")
        self._path = path
        self._target = None

    def capabilities(self) -> Capabilities:
        target = self._load()
        report = getattr(target, "capabilities", None)
        if callable(report):
            value = report()
            if isinstance(value, Capabilities):
                return value
        return Capabilities(False, False, False, False)

    def run_query(self, request: QueryRequest) -> Trace:
        if os.environ.get("EVAL_ALLOW_PYTHON_ADAPTERS") != "1":
            return error_trace(request, "Python adapters are disabled")
        try:
            target = self._load()
            result = target.run_query(request)
        except Exception as exc:
            return error_trace(request, redact(str(exc)))
        if isinstance(result, Trace):
            result.test_case_id = result.test_case_id or request.test_case_id
            result.question = result.question or request.question
            return result
        return error_trace(request, "Python adapter did not return a Trace")

    def _load(self):
        if self._target is not None:
            return self._target
        module_name, _, qualname = self._path.partition(":")
        module = importlib.import_module(module_name)
        obj = module
        for part in qualname.split("."):
            obj = getattr(obj, part)
        self._target = obj() if isinstance(obj, type) else obj
        return self._target
