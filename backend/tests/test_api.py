from fastapi.testclient import TestClient

from app.domain.models import Project
from app.main import create_app
from tests.support import AdapterBox, open_container


def test_database_uses_wal_and_projects_persist(tmp_path, monkeypatch):
    monkeypatch.setenv("EVAL_SECRET_KEY", "test-secret-key")
    box = AdapterBox()
    app = create_app(
        f"sqlite:///{tmp_path / 'api.db'}",
        judge=None,
        adapter_factories={"fake": box.factory},
    )
    # create_app always builds AgnoJudge when judge is None. Override after the fact
    # is unnecessary here: this test only touches projects.
    client = TestClient(app)
    created = client.post("/api/projects", json={"name": "Support"})
    assert created.status_code == 200
    body = created.json()
    listed = client.get("/api/projects")
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == body["id"]
    with app.state.container.engine.connect() as connection:
        journal = connection.exec_driver_sql("PRAGMA journal_mode").scalar()
        synchronous = connection.exec_driver_sql("PRAGMA synchronous").scalar()
        timeout = connection.exec_driver_sql("PRAGMA busy_timeout").scalar()
    assert journal.lower() == "wal"
    assert synchronous == 1
    assert timeout == 5000
    stored = app.state.container.repository.get(Project, body["id"])
    assert stored is not None
    assert stored.name == "Support"


def test_compare_rejects_different_datasets(tmp_path, monkeypatch):
    container, _box, _judge = open_container(tmp_path, monkeypatch)
    from tests.support import seed, start_run

    project, config, first = seed(
        container,
        "question,expected_answer,gold_passage\nWhat is the refund window?,30 days,alpha beta gamma delta\n",
    )
    second = container.dataset_service.import_file(
        project.id,
        "other.csv",
        b"question,expected_answer,gold_passage\nOther?,yes,alpha beta gamma delta\n",
    ).dataset
    run_a = start_run(container, project, first, config)
    run_b = start_run(container, project, second, config)
    container.run_service.execute(run_a.id)
    container.run_service.execute(run_b.id)
    app = create_app(
        f"sqlite:///{tmp_path / 'unused.db'}",
        judge=container.judge,
        secondary_judge=container.judge,
        adapter_factories=container.adapter_factories,
    )
    app.state.container = container
    client = TestClient(app)
    response = client.get("/api/runs/compare", params={"run_a": run_a.id, "run_b": run_b.id})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "dataset_mismatch"
    html = client.get(f"/api/runs/{run_a.id}/report.html")
    assert html.status_code == 200
    text = html.text
    for title in (
        "Run header",
        "Score summary",
        "What could not be measured",
        "Failure-cause counts",
        "Findings",
        "Setup table",
        "Compare block",
        "Calibration banner",
    ):
        assert f"<h2>{title}</h2>" in text
    report = client.get(f"/api/runs/{run_a.id}/report").json()
    assert [finding["cause"] for finding in report["findings"]]
    assert "not-a-real-finding" not in text


def test_deleted_dataset_leaves_the_list_and_its_runs(tmp_path, monkeypatch):
    container, _box, _judge = open_container(tmp_path, monkeypatch)
    from tests.support import seed, start_run

    project, config, dataset = seed(container, "question,expected_answer\nWhat is the refund window?,30 days\n")
    extra = container.dataset_service.import_file(project.id, "extra.csv", b"question\nSpare?\n").dataset
    run = start_run(container, project, dataset, config)
    app = create_app(
        f"sqlite:///{tmp_path / 'unused.db'}",
        judge=container.judge,
        secondary_judge=container.judge,
        adapter_factories=container.adapter_factories,
    )
    app.state.container = container
    client = TestClient(app)
    blocked = client.delete(f"/api/datasets/{dataset.id}")
    assert blocked.status_code == 422
    assert client.get(f"/api/projects/{project.id}/datasets").json()
    container.run_service.execute(run.id)
    deleted = client.delete(f"/api/datasets/{dataset.id}")
    assert deleted.status_code == 204
    remaining = client.get(f"/api/projects/{project.id}/datasets").json()
    assert [item["id"] for item in remaining] == [extra.id]
    assert client.get(f"/api/datasets/{dataset.id}").status_code == 404
    assert client.get(f"/api/runs/{run.id}").status_code == 404
    assert client.delete(f"/api/datasets/{dataset.id}").status_code == 404


def test_probe_sends_the_query_the_user_typed(tmp_path, monkeypatch):
    monkeypatch.setenv("EVAL_SECRET_KEY", "test-secret-key")
    box = AdapterBox()
    app = create_app(f"sqlite:///{tmp_path / 'probe.db'}", judge=None, adapter_factories={"fake": box.factory})
    client = TestClient(app)
    project = client.post("/api/projects", json={"name": "Bench"}).json()
    system = client.post(f"/api/projects/{project['id']}/systems", json={"name": "Target"}).json()
    config = client.post(
        f"/api/systems/{system['id']}/configs",
        json={"adapter_type": "fake", "adapter_settings": {}, "profile_settings": {}, "auth_secret": None},
    ).json()
    sent = client.post(f"/api/system-configs/{config['id']}/probe", json={"question": "What does Article 10.7 say?"})
    assert sent.status_code == 200
    assert sent.json()["answer"] == "30 days"
    assert box.calls[-1].question == "What does Article 10.7 say?"
    blank = client.post(f"/api/system-configs/{config['id']}/probe", json={"question": "   "})
    assert blank.status_code == 422
    untouched = client.post(f"/api/system-configs/{config['id']}/probe")
    assert untouched.status_code == 200
    assert box.calls[-1].question == "ping"
