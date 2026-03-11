from __future__ import annotations

from pathlib import Path
from threading import current_thread
from time import sleep

import job_search.ingest as ingest_module
from job_search.enums import ApplicationStatus
from job_search.ingest import IngestionService
from job_search.models import ApplicationUpdate, NormalizedJob
from job_search.repository import Repository
from job_search.scoring import (
    classify_role_tags,
    extract_language_signals,
    matches_search_profile,
    score_job,
)
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


def test_role_classification_covers_forward_deployment_and_applied_science() -> None:
    tags = classify_role_tags(
        "Forward Deployed Engineer building applied machine learning systems with research engineers"
    )
    assert "forward_deployment" in tags
    assert "applied_scientist" in tags
    assert "research_engineering" in tags
    assert "ml" in tags


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


def test_search_profile_does_not_false_positive_short_excluded_terms_inside_words() -> None:
    job = NormalizedJob(
        source_name="google",
        source_job_id="123",
        canonical_url="https://example.com/jobs/123",
        company="Google",
        title="Software Engineer III, Infrastructure, YouTube",
        location_text="Switzerland",
        country="CH",
        description_text="Build large-scale infrastructure and distributed systems.",
        requirements_text="Experience with hardware architecture and storage systems.",
        role_tags=["backend", "distributed_systems", "platform"],
    )
    profile = {
        "target_countries": ["CH", "DE", "NL", "RO"],
        "excluded_keywords": ["hr"],
        "required_role_tags_any": ["backend", "ml"],
    }
    assert matches_search_profile(job, profile)


def test_search_profile_allows_broad_software_roles_without_tag_intersection() -> None:
    job = NormalizedJob(
        source_name="example",
        source_job_id="456",
        canonical_url="https://example.com/jobs/456",
        company="Example",
        title="Software Engineer III, Infrastructure",
        location_text="Zurich, Switzerland",
        country="CH",
        description_text="Build reliable production infrastructure and large-scale systems.",
        requirements_text="2 years of software development experience.",
        role_tags=[],
    )
    profile = {
        "target_countries": ["CH", "DE", "NL", "RO"],
        "excluded_keywords": ["sales", "marketing", "hr"],
        "required_role_tags_any": ["ml", "backend", "platform"],
    }
    assert matches_search_profile(job, profile)


def test_extract_language_signals_detects_required_languages() -> None:
    signals = extract_language_signals(
        "Senior Software Engineer",
        "English proficiency is a requirement for all roles. German is preferred.",
        "Must speak Dutch when working with local customers.",
    )
    assert "English required" in signals
    assert "German preferred" in signals
    assert "Dutch required" in signals


def test_revalidation_refreshes_language_signals(tmp_path: Path) -> None:
    service = JobSearchService(repository=build_repo(tmp_path))
    job = NormalizedJob(
        source_name="google",
        source_job_id="789",
        canonical_url="https://example.com/jobs/789",
        company="Google",
        title="Software Engineer III, Infrastructure, YouTube",
        location_text="Zurich, Switzerland",
        country="CH",
        description_text="Build reliable backend systems.",
        requirements_text="English proficiency is a requirement for all roles.",
        role_tags=["backend"],
    )
    job.score, job.score_reasons = score_job(
        job,
        {"adapter": "google_careers", "careers_url": "https://careers.google.com/"},
        {"priority_keywords": ["backend"]},
    )
    job_id, _ = service.repository.upsert_job(job)
    service.repository.refresh_job_profile_fields(job_id, is_active=True, language_signals=[])

    service._revalidate_jobs()

    refreshed = service.get_job(job_id)
    assert refreshed is not None
    assert "English required" in refreshed.language_signals


def test_ingestion_runs_multiple_sources_in_parallel(tmp_path: Path, monkeypatch) -> None:
    thread_names: set[str] = set()

    class SlowAdapter:
        def __init__(self, source_config: dict):
            self.source_config = source_config

        def discover_openings(self):
            thread_names.add(current_thread().name)
            sleep(0.05)
            return [
                type(
                    "Listing",
                    (),
                    {
                        "external_id": f"{self.source_config['name']}-1",
                        "title": "Senior Backend Engineer",
                        "url": f"https://example.com/{self.source_config['name']}/1",
                        "location_text": "Berlin, Germany",
                        "metadata": {},
                    },
                )()
            ]

        def fetch_job(self, listing):
            sleep(0.05)
            return type(
                "Payload",
                (),
                {
                    "source_name": self.source_config["name"],
                    "source_job_id": listing.external_id,
                    "canonical_url": listing.url,
                    "payload": {},
                },
            )()

        def normalize(self, payload):
            return NormalizedJob(
                source_name=payload.source_name,
                source_job_id=payload.source_job_id,
                canonical_url=payload.canonical_url,
                company=self.source_config["company_name"],
                title="Senior Backend Engineer",
                location_text="Berlin, Germany",
                country="DE",
                description_text="Backend platform role",
            )

    monkeypatch.setattr(
        "job_search.ingest.load_active_company_targets",
        lambda: [
            {
                "name": "source-a",
                "company_name": "A",
                "adapter": "slow",
                "country": "DE",
                "employer_class": "enterprise",
            },
            {
                "name": "source-b",
                "company_name": "B",
                "adapter": "slow",
                "country": "DE",
                "employer_class": "enterprise",
            },
            {
                "name": "source-c",
                "company_name": "C",
                "adapter": "slow",
                "country": "DE",
                "employer_class": "enterprise",
            },
        ],
    )
    monkeypatch.setattr("job_search.ingest.load_profile", lambda: {"target_countries": ["DE"]})
    monkeypatch.setitem(ingest_module.ADAPTERS, "slow", SlowAdapter)
    monkeypatch.setenv("JOB_SEARCH_INGEST_WORKERS", "3")

    summaries = IngestionService(build_repo(tmp_path)).run()

    assert len(summaries) == 3
    assert len(thread_names) >= 2


def test_ingestion_skips_disabled_sources_by_default(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "job_search.ingest.load_active_company_targets",
        lambda: [
            {
                "name": "source-a",
                "company_name": "A",
                "adapter": "mock",
                "country": "DE",
                "employer_class": "enterprise",
                "jobs": [],
            }
        ],
    )
    monkeypatch.setattr("job_search.ingest.load_profile", lambda: {"target_countries": ["DE"]})

    summaries = IngestionService(build_repo(tmp_path)).run()

    assert [summary.source_name for summary in summaries] == ["source-a"]


def test_service_lists_sources_with_metrics(tmp_path: Path) -> None:
    service = JobSearchService(repository=build_repo(tmp_path))
    service.run_once(source_names=["demo-google"])

    sources = service.list_sources(include_demo=True)
    google = next(source for source in sources if source["name"] == "demo-google")

    assert google["enabled"] is True
    assert google["run_count"] == 1
    assert google["success_rate"] == 1.0
    assert google["last_run_status"] == "success"
    assert google["discovered_total"] == 1
    assert google["inserted_total"] == 1
    assert google["retained_job_count"] == 1
    assert google["yield_rate"] == 1.0
