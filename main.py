"""Start the evaluation API from the repository root: uv run main.py."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_BACKEND = _ROOT / "backend"
_ENV_FILE = _ROOT / ".env"


def load_env(path: Path) -> None:
    """Load KEY=VALUE lines from path. Existing environment variables win."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ[key] = value


def main() -> None:
    load_env(_ENV_FILE)
    backend = str(_BACKEND)
    if backend not in sys.path:
        sys.path.insert(0, backend)
    from app.main import serve

    serve()


if __name__ == "__main__":
    main()
