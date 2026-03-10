from __future__ import annotations

from dataclasses import dataclass

from job_search.adapters import (
    AmazonJobsAdapter,
    AppleJobsAdapter,
    ArbeitnowAdapter,
    GoogleCareersAdapter,
    GreenhouseAdapter,
    LeverAdapter,
    MockAdapter,
    SmartRecruitersAdapter,
    WorkdayAdapter,
)
from job_search.config import load_active_company_targets, load_company_targets, load_profile
from job_search.enums import EmployerClass
from job_search.repository import Repository
from job_search.scoring import matches_search_profile, score_job


ADAPTERS = {
    "amazon_jobs": AmazonJobsAdapter,
    "apple_jobs": AppleJobsAdapter,
    "arbeitnow": ArbeitnowAdapter,
    "google_careers": GoogleCareersAdapter,
    "greenhouse": GreenhouseAdapter,
    "lever": LeverAdapter,
    "mock": MockAdapter,
    "smartrecruiters": SmartRecruitersAdapter,
    "workday": WorkdayAdapter,
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
        summaries: list[IngestionSummary] = []
        source_configs = load_company_targets() if source_names else load_active_company_targets()
        for source_config in source_configs:
            if source_names and source_config["name"] not in source_names:
                continue
            summaries.append(self._run_source(source_config))
        return summaries

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
