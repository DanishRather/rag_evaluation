import threading
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.pool import NullPool


def set_pragmas(dbapi_connection, _record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def ensure_sqlite_path(url: str) -> None:
    if not url.startswith("sqlite:///"):
        return
    location = url.removeprefix("sqlite:///")
    if location in {":memory:", ""} or location.startswith("file:"):
        return
    Path(location).expanduser().parent.mkdir(parents=True, exist_ok=True)


def make_engine(url: str) -> tuple[Engine, threading.RLock]:
    ensure_sqlite_path(url)
    engine = create_engine(url, connect_args={"check_same_thread": False}, poolclass=NullPool)
    event.listen(engine, "connect", set_pragmas)
    return engine, threading.RLock()
