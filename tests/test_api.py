from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from job_search.api import create_app
from job_search.config import load_company_targets
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
    service = JobSearchService(repository=Repository(tmp_path / "jobs.db"))
    service.run_once(source_names=["demo-google"])
    app = create_app(service)
    client = TestClient(app)

    response = client.get("/sources")
    assert response.status_code == 200
    body = response.json()
    asml = next(item for item in body["items"] if item["name"] == "asml")
    delivery_hero = next(item for item in body["items"] if item["name"] == "delivery-hero")
    deepmind = next(item for item in body["items"] if item["name"] == "deepmind")
    jane_street = next(item for item in body["items"] if item["name"] == "jane-street")
    meta = next(item for item in body["items"] if item["name"] == "meta")
    spotify = next(item for item in body["items"] if item["name"] == "spotify")
    assert asml["company_name"] == "ASML"
    assert delivery_hero["enabled"] is True
    assert deepmind["company_name"] == "DeepMind"
    assert jane_street["company_name"] == "Jane Street"
    assert meta["company_name"] == "Meta"
    assert spotify["company_name"] == "Spotify"
    assert "yield_rate" in delivery_hero


def test_api_excludes_disabled_sources_from_default_listing(tmp_path: Path) -> None:
    app = create_app(JobSearchService(repository=Repository(tmp_path / "jobs.db")))
    client = TestClient(app)

    response = client.get("/sources")
    assert response.status_code == 200
    names = {item["name"] for item in response.json()["items"]}
    assert "arbeitnow-de" not in names


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


def test_api_creates_disabled_source(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("job_search.config.LOCAL_TARGETS_PATH", tmp_path / "company_targets.local.json")
    load_company_targets.cache_clear()
    app = create_app(JobSearchService(repository=Repository(tmp_path / "jobs.db")))
    client = TestClient(app)

    response = client.post(
        "/sources",
        json={
            "name": "custom-source",
            "company_name": "Custom",
            "adapter": "greenhouse",
            "country": "DE",
            "employer_class": "enterprise",
            "enabled": False,
            "careers_url": "https://example.com/careers",
            "board_token": "custom",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is False
    load_company_targets.cache_clear()


def test_api_updates_source_enabled_flag(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("job_search.config.LOCAL_TARGETS_PATH", tmp_path / "company_targets.local.json")
    load_company_targets.cache_clear()
    app = create_app(JobSearchService(repository=Repository(tmp_path / "jobs.db")))
    client = TestClient(app)

    response = client.put(
        "/sources/arbeitnow-de",
        json={
            "name": "arbeitnow-de",
            "company_name": "Arbeitnow",
            "adapter": "arbeitnow",
            "country": "DE",
            "employer_class": "other",
            "enabled": True,
            "priority_weight": 2,
            "careers_url": "https://www.arbeitnow.com/",
            "max_pages": 2,
        },
    )
    assert response.status_code == 200
    assert response.json()["enabled"] is True
    load_company_targets.cache_clear()


def test_api_reports_run_status(tmp_path: Path) -> None:
    app = create_app(JobSearchService(repository=Repository(tmp_path / "jobs.db")))
    client = TestClient(app)

    response = client.get("/runs/status")
    assert response.status_code == 200
    assert response.json() == {
        "running": False,
        "running_sources": [],
        "completed_sources": 0,
        "total_sources": 0,
        "failed_sources": [],
    }


def test_service_marks_stale_running_rows_abandoned(tmp_path: Path) -> None:
    repository = Repository(tmp_path / "jobs.db")
    run_id = repository.create_run("stale-source")

    service = JobSearchService(repository=repository)
    assert service.run_status() == {
        "running": False,
        "running_sources": [],
        "completed_sources": 0,
        "total_sources": 0,
        "failed_sources": [],
    }

    runs = service.list_runs()
    stale_run = next(run for run in runs if run.id == run_id)
    assert stale_run.status == "abandoned"
    assert stale_run.finished_at is not None
