from __future__ import annotations

from dataclasses import dataclass
import os
from concurrent.futures import ThreadPoolExecutor

from job_search.adapters import (
    AshbyAdapter,
    AmazonJobsAdapter,
    AppleJobsAdapter,
    ArbeitnowAdapter,
    AsmlJobsAdapter,
    BookingJobsAdapter,
    EightfoldAdapter,
    GoogleCareersAdapter,
    GreenhouseAdapter,
    JaneStreetJobsAdapter,
    LeverAdapter,
    MetaCareersAdapter,
    MicrosoftCareersAdapter,
    MockAdapter,
    RevolutJobsAdapter,
    SmartRecruitersAdapter,
    SpotifyJobsAdapter,
    UberJobsAdapter,
    WiseJobsAdapter,
    WorkdayAdapter,
    ZalandoJobsAdapter,
)
from job_search.config import load_active_company_targets, load_company_targets, load_profile
from job_search.enums import EmployerClass
from job_search.repository import Repository
from job_search.scoring import matches_search_profile, score_job


ADAPTERS = {
    "ashby": AshbyAdapter,
    "amazon_jobs": AmazonJobsAdapter,
    "apple_jobs": AppleJobsAdapter,
    "arbeitnow": ArbeitnowAdapter,
    "asml_jobs": AsmlJobsAdapter,
    "booking_jobs": BookingJobsAdapter,
    "eightfold": EightfoldAdapter,
    "google_careers": GoogleCareersAdapter,
    "greenhouse": GreenhouseAdapter,
    "jane_street_jobs": JaneStreetJobsAdapter,
    "lever": LeverAdapter,
    "meta_careers": MetaCareersAdapter,
    "microsoft_careers": MicrosoftCareersAdapter,
    "mock": MockAdapter,
    "revolut_jobs": RevolutJobsAdapter,
    "smartrecruiters": SmartRecruitersAdapter,
    "spotify_jobs": SpotifyJobsAdapter,
    "uber_jobs": UberJobsAdapter,
    "wise_jobs": WiseJobsAdapter,
    "workday": WorkdayAdapter,
    "zalando_jobs": ZalandoJobsAdapter,
}


@dataclass
class IngestionSummary:
    source_name: str
    discovered_count: int = 0
    inserted_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0


class IngestionService:
    def __init__(self, repository: Repository):
        self.repository = repository
        self.repository.save_searches()

    def run(self, source_names: list[str] | None = None) -> list[IngestionSummary]:
        self.profile = load_profile()
        source_configs = load_company_targets() if source_names else load_active_company_targets()
        selected_sources = [
            source_config
            for source_config in source_configs
            if not source_names or source_config["name"] in source_names
        ]
        if not selected_sources:
            return []
        if len(selected_sources) == 1:
            return [self._run_source(selected_sources[0])]

        max_workers = _worker_count(len(selected_sources))
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="job-search-source") as executor:
            futures = [executor.submit(self._run_source, source_config) for source_config in selected_sources]
            return [future.result() for future in futures]

    def _run_source(self, source_config: dict) -> IngestionSummary:
        run_id = self.repository.create_run(source_config["name"])
        summary = IngestionSummary(source_name=source_config["name"])
        adapter_cls = ADAPTERS[source_config["adapter"]]
        adapter = adapter_cls(source_config)
        try:
            listings = adapter.discover_openings()
            summary.discovered_count = len(listings)
            for listing in listings:
                payload = adapter.fetch_job(listing)
                normalized = adapter.normalize(payload)
                normalized.employer_class = EmployerClass(source_config["employer_class"])
                normalized.score, normalized.score_reasons = score_job(normalized, source_config, self.profile)
                if not matches_search_profile(normalized, self.profile):
                    summary.skipped_count += 1
                    continue
                _, action = self.repository.upsert_job(normalized)
                if action == "inserted":
                    summary.inserted_count += 1
                else:
                    summary.updated_count += 1
            self.repository.finish_run(
                run_id,
                status="success",
                discovered_count=summary.discovered_count,
                inserted_count=summary.inserted_count,
                updated_count=summary.updated_count,
                skipped_count=summary.skipped_count,
            )
        except Exception as exc:  # noqa: BLE001
            self.repository.finish_run(
                run_id,
                status="failed",
                discovered_count=summary.discovered_count,
                inserted_count=summary.inserted_count,
                updated_count=summary.updated_count,
                skipped_count=summary.skipped_count,
                error_text=str(exc),
            )
        return summary


def _worker_count(source_count: int) -> int:
    configured = os.getenv("JOB_SEARCH_INGEST_WORKERS")
    if configured:
        try:
            return max(1, min(source_count, int(configured)))
        except ValueError:
            pass
    return max(1, min(source_count, 6))
