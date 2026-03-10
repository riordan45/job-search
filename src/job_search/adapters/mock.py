from __future__ import annotations

from datetime import datetime

from job_search.adapters.base import SourceAdapter
from job_search.enums import Country, EmployerClass
from job_search.models import NormalizedJob, RawJobPayload, SourceListing
from job_search.scoring import infer_remote_mode


class MockAdapter(SourceAdapter):
    def discover_openings(self) -> list[SourceListing]:
        listings = []
        for item in self.source_config.get("jobs", []):
            listings.append(
                SourceListing(
                    external_id=item["id"],
                    title=item["title"],
                    url=item["url"],
                    location_text=item["location_text"],
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
        text = item["title"] + " " + item["description_text"]
        return NormalizedJob(
            source_name=payload.source_name,
            source_job_id=payload.source_job_id,
            canonical_url=payload.canonical_url,
            company=self.source_config["company_name"],
            title=item["title"],
            location_text=item["location_text"],
            country=Country(self.source_config["country"]),
            remote_mode=infer_remote_mode(text),
            posted_at=datetime.fromisoformat(item["posted_at"]),
            description_text=item["description_text"],
            requirements_text=item.get("requirements_text", ""),
            seniority=item.get("seniority"),
            employer_class=EmployerClass(self.source_config["employer_class"]),
            language_signals=item.get("language_signals", ["en"]),
        )
