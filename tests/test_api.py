from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from job_search.api import create_app
from job_search.repository import Repository
from job_search.service import JobSearchService


def test_api_lists_jobs_after_run(tmp_path: Path) -> None:
    repository = Repository(tmp_path / "jobs.db")
    service = JobSearchService(repository=repository)
    service.run_once(source_names=["demo-google", "demo-optiver"])

    app = create_app(service)
    client = TestClient(app)
    response = client.get("/jobs?include_demo=true")
    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) >= 2


def test_api_exposes_sources(tmp_path: Path) -> None:
    app = create_app(JobSearchService(repository=Repository(tmp_path / "jobs.db")))
    client = TestClient(app)

    response = client.get("/sources")
    assert response.status_code == 200
    body = response.json()
    assert any(item["name"] == "delivery-hero" for item in body["items"])


def test_api_creates_saved_search(tmp_path: Path) -> None:
    app = create_app(JobSearchService(repository=Repository(tmp_path / "jobs.db")))
    client = TestClient(app)

    response = client.post(
        "/saved-searches",
        json={"name": "Romania Backend", "filters": {"country": "RO", "role_tags": ["backend"]}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Romania Backend"


def test_api_reports_run_status(tmp_path: Path) -> None:
    app = create_app(JobSearchService(repository=Repository(tmp_path / "jobs.db")))
    client = TestClient(app)

    response = client.get("/runs/status")
    assert response.status_code == 200
    assert response.json() == {"running": False}


def test_service_marks_stale_running_rows_abandoned(tmp_path: Path) -> None:
    repository = Repository(tmp_path / "jobs.db")
    run_id = repository.create_run("stale-source")

    service = JobSearchService(repository=repository)
    assert service.run_status() == {"running": False}

    runs = service.list_runs()
    stale_run = next(run for run in runs if run.id == run_id)
    assert stale_run.status == "abandoned"
    assert stale_run.finished_at is not None
