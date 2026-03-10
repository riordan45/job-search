from __future__ import annotations

from pathlib import Path

from job_search.enums import ApplicationStatus
from job_search.models import ApplicationUpdate, NormalizedJob
from job_search.repository import Repository
from job_search.scoring import classify_role_tags, matches_search_profile, score_job
from job_search.service import JobSearchService


def build_repo(tmp_path: Path) -> Repository:
    return Repository(tmp_path / "jobs.db")


def test_role_classification_covers_target_keywords() -> None:
    tags = classify_role_tags(
        "Senior software engineer for Kubernetes platform and distributed systems with LLM infra"
    )
    assert "backend" in tags
    assert "kubernetes" in tags
    assert "platform" in tags
    assert "llm_infra" in tags


def test_dedupe_updates_same_fingerprint(tmp_path: Path) -> None:
    repository = build_repo(tmp_path)
    first = NormalizedJob(
        source_name="demo",
        source_job_id="1",
        canonical_url="https://example.com/jobs/1",
        company="Google",
        title="Senior Backend Engineer",
        location_text="Zurich, Switzerland",
        country="CH",
        description_text="Backend distributed systems",
    )
    second = first.model_copy(
        update={
            "source_job_id": "2",
            "canonical_url": "https://example.com/jobs/repost-1",
        }
    )
    _, first_action = repository.upsert_job(first)
    _, second_action = repository.upsert_job(second)

    assert first_action == "inserted"
    assert second_action == "updated"
    assert len(repository.list_jobs()) == 1


def test_application_state_survives_reingestion(tmp_path: Path) -> None:
    service = JobSearchService(repository=build_repo(tmp_path))
    service.run_once(source_names=["demo-google"])
    jobs = service.list_jobs(include_demo=True)
    job_id = jobs[0].id

    service.update_application(job_id, ApplicationUpdate(status=ApplicationStatus.APPLIED, notes="sent"))
    service.run_once(source_names=["demo-google"])

    refreshed = service.get_job(job_id)
    assert refreshed is not None
    assert refreshed.application_status == ApplicationStatus.APPLIED
    assert refreshed.application_notes == "sent"


def test_netherlands_finance_jobs_get_boost() -> None:
    job = NormalizedJob(
        source_name="demo",
        source_job_id="1",
        canonical_url="https://example.com/jobs/1",
        company="Optiver",
        title="Backend Engineer",
        location_text="Amsterdam, Netherlands",
        country="NL",
        description_text="Python backend systems",
        employer_class="finance",
    )
    company_target = {"priority_weight": 5}
    profile = {"priority_keywords": ["python", "backend"]}
    score, reasons = score_job(job, company_target, profile)
    assert score > 0
    assert "nl-finance-boost" in reasons


def test_company_hosted_postings_get_priority_boost() -> None:
    job = NormalizedJob(
        source_name="sumup",
        source_job_id="1",
        canonical_url="https://careers.sumup.com/positions/1",
        company="SumUp",
        title="Senior Software Engineer",
        location_text="Berlin, Germany",
        country="DE",
        description_text="Backend distributed systems",
        employer_class="finance",
    )
    score, reasons = score_job(
        job,
        {
            "adapter": "greenhouse",
            "careers_url": "https://careers.sumup.com/",
            "priority_weight": 5,
        },
        {"priority_keywords": ["backend"]},
    )
    assert score > 0
    assert job.source_kind == "direct_company_page"
    assert job.source_priority > 0
    assert "company-page-primary" in reasons


def test_search_profile_filters_out_irrelevant_roles() -> None:
    job = NormalizedJob(
        source_name="demo",
        source_job_id="1",
        canonical_url="https://example.com/jobs/1",
        company="Example",
        title="Account Executive",
        location_text="Berlin, Germany",
        country="DE",
        description_text="Sales role",
        role_tags=[],
    )
    profile = {
        "target_countries": ["DE"],
        "excluded_keywords": ["sales", "account executive"],
        "required_role_tags_any": ["backend", "ml"],
    }
    assert not matches_search_profile(job, profile)


def test_dedupe_keeps_higher_trust_source_metadata(tmp_path: Path) -> None:
    repository = build_repo(tmp_path)
    first = NormalizedJob(
        source_name="sumup",
        source_job_id="1",
        canonical_url="https://careers.sumup.com/positions/1",
        company="SumUp",
        title="Senior Software Engineer",
        location_text="Berlin, Germany",
        country="DE",
        description_text="Backend distributed systems",
        source_kind="direct_company_page",
        source_priority=40,
    )
    second = first.model_copy(
        update={
            "source_name": "arbeitnow-de",
            "source_job_id": "agg-1",
            "canonical_url": "https://www.arbeitnow.com/jobs/sumup-1",
            "source_kind": "aggregator",
            "source_priority": 0,
        }
    )

    repository.upsert_job(first)
    repository.upsert_job(second)

    job = repository.list_jobs()[0]
    assert job.source_name == "sumup"
    assert job.canonical_url == "https://careers.sumup.com/positions/1"
    assert job.source_kind == "direct_company_page"


def test_search_profile_filters_out_mixed_foreign_locations() -> None:
    job = NormalizedJob(
        source_name="demo",
        source_job_id="2",
        canonical_url="https://example.com/jobs/2",
        company="Example",
        title="Principal Machine Learning Engineer",
        location_text="Amsterdam, Netherlands; Chicago, United States",
        country="NL",
        description_text="Machine learning platform role",
        role_tags=["ml", "platform"],
    )
    profile = {
        "target_countries": ["CH", "DE", "NL", "RO"],
        "excluded_keywords": [],
        "required_role_tags_any": ["ml", "backend"],
    }
    assert not matches_search_profile(job, profile)


def test_search_profile_filters_out_mixed_city_locations_without_country_code() -> None:
    job = NormalizedJob(
        source_name="demo",
        source_job_id="3",
        canonical_url="https://example.com/jobs/3",
        company="Example",
        title="Senior Backend Engineer",
        location_text="Berlin, Barcelona",
        country="DE",
        description_text="Backend platform role",
        role_tags=["backend", "platform"],
    )
    profile = {
        "target_countries": ["CH", "DE", "NL", "RO"],
        "excluded_keywords": [],
        "required_role_tags_any": ["backend", "ml"],
    }
    assert not matches_search_profile(job, profile)


def test_search_profile_filters_out_global_remote_regions() -> None:
    job = NormalizedJob(
        source_name="demo",
        source_job_id="4",
        canonical_url="https://example.com/jobs/4",
        company="Example",
        title="Senior Backend Engineer",
        location_text="Remote-EMEA GLOBAL Romania Germany Spain",
        country="DE",
        description_text="Backend platform role",
        role_tags=["backend", "platform"],
    )
    profile = {
        "target_countries": ["CH", "DE", "NL", "RO"],
        "excluded_keywords": [],
        "required_role_tags_any": ["backend", "ml"],
    }
    assert not matches_search_profile(job, profile)
