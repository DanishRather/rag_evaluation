import pytest

from app.main import create_container


@pytest.fixture
def container(tmp_path, monkeypatch):
    monkeypatch.setenv("EVAL_SECRET_KEY", "test-secret-key")
    url = f"sqlite:///{tmp_path / 'eval.db'}"
    return create_container(url)
