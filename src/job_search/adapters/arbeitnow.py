from __future__ import annotations

from datetime import datetime, timezone

from job_search.adapters.base import SourceAdapter
from job_search.adapters.http import fetch_json
from job_search.enums import Country, EmployerClass
from job_search.models import NormalizedJob, RawJobPayload, SourceListing
from job_search.scoring import detect_country, infer_remote_mode


class ArbeitnowAdapter(SourceAdapter):
    def discover_openings(self) -> list[SourceListing]:
        max_pages = int(self.source_config.get("max_pages", 2))
        listings: list[SourceListing] = []
        for page in range(1, max_pages + 1):
            data = fetch_json(f"https://www.arbeitnow.com/api/job-board-api?page={page}")
            for item in data.get("data", []):
                listings.append(
                    SourceListing(
                        external_id=item["slug"],
                        title=item["title"],
                        url=item["url"],
                        location_text=item.get("location", ""),
                        metadata=item,
                    )
                )
        return listings

    def fetch_job(self, listing: SourceListing) -> RawJobPayload:
        return RawJobPayload(
            source_name=self.source_config["name"],
            source_job_id=listing.external_id,
            canonical_url=listing.url,
            payload=listing.metadata,
        )

    def normalize(self, payload: RawJobPayload) -> NormalizedJob:
        item = payload.payload
        text = f'{item.get("title", "")} {item.get("description", "")} {" ".join(item.get("tags", []))}'
        country = detect_country(
            f'{item.get("location", "")} {item.get("url", "")} {item.get("description", "")}',
            default=self.source_config.get("country"),
        )
        return NormalizedJob(
            source_name=payload.source_name,
            source_job_id=payload.source_job_id,
            canonical_url=payload.canonical_url,
            company=item["company_name"],
            title=item["title"],
            location_text=item.get("location", ""),
            country=Country(country or self.source_config["country"]),
            employment_type=", ".join(item.get("job_types", [])) or None,
            remote_mode="remote" if item.get("remote") else infer_remote_mode(text),
            posted_at=datetime.fromtimestamp(item["created_at"], tz=timezone.utc),
            description_text=item.get("description", ""),
            requirements_text=" ".join(item.get("tags", [])),
            seniority=None,
            employer_class=EmployerClass(self.source_config["employer_class"]),
            language_signals=["en"],
        )
