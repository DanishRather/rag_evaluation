import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "backend" / "app"
FRONTEND = ROOT / "frontend" / "src"


def _hits(pattern: str, root: Path, suffix: str) -> list[str]:
    found = []
    if not root.exists():
        return found
    for path in root.rglob(f"*{suffix}"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if pattern in text:
            found.append(str(path.relative_to(ROOT)))
    return found


def test_forbidden_backend_patterns_stay_out_of_application_code():
    assert _hits("adapter_type ==", APP, ".py") == []
    assert _hits("metric_name ==", APP, ".py") == []
    needle = "SqliteRunRepository" + "("
    repository = _hits(needle, ROOT / "backend", ".py")
    assert repository == ["backend/app/main.py"]
    for path in (APP / "api").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in ("app.infrastructure", "app.security", "import agno", "from agno", "sqlalchemy"):
            assert token not in text, path
    agno_importers = []
    for path in APP.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "import agno" in text or "from agno" in text:
            agno_importers.append(path.relative_to(ROOT).as_posix())
    assert agno_importers == ["backend/app/infrastructure/judge/agno_judge.py"]


def test_import_linter_contracts_hold():
    completed = subprocess.run(
        [str(Path(sys.executable).with_name("lint-imports"))],
        cwd=ROOT,
        env={**dict(**{k: v for k, v in __import__("os").environ.items()}), "PYTHONPATH": str(ROOT / "backend")},
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_frontend_fetch_stays_in_the_http_client():
    client = FRONTEND / "http" / "HttpApiClient.ts"
    if not client.exists():
        return
    illegal = []
    for folder in ("view", "controller", "services"):
        root = FRONTEND / folder
        for path in root.rglob("*"):
            if path.suffix not in {".ts", ".tsx"}:
                continue
            text = path.read_text(encoding="utf-8")
            if re.search(r"\bfetch\(", text) or "EventSource" in text:
                illegal.append(str(path.relative_to(ROOT)))
    assert illegal == []
    callers = []
    for path in FRONTEND.rglob("*"):
        if path.suffix not in {".ts", ".tsx"}:
            continue
        text = path.read_text(encoding="utf-8")
        if re.search(r"\bfetch\(", text) or "EventSource" in text or "new HttpApiClient" in text:
            callers.append(path.relative_to(ROOT).as_posix())
    assert sorted(callers) == [
        "frontend/src/http/HttpApiClient.ts",
        "frontend/src/main.tsx",
    ]
