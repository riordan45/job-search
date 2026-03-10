from __future__ import annotations

from datetime import datetime

from job_search.adapters.base import SourceAdapter
from job_search.adapters.http import post_json
from job_search.enums import Country, EmployerClass
from job_search.models import NormalizedJob, RawJobPayload, SourceListing
from job_search.scoring import detect_country


TARGET_COUNTRIES = ["Germany", "Netherlands", "Romania", "Switzerland"]


class WorkdayAdapter(SourceAdapter):
    def discover_openings(self) -> list[SourceListing]:
        endpoint = self.source_config["api_url"]
        facets = post_json(endpoint, {"limit": 1, "offset": 0})
        country_ids = _country_facet_ids(facets, self.source_config.get("target_country_names", TARGET_COUNTRIES))

        limit = int(self.source_config.get("limit", 20))
        offset = 0
        listings: list[SourceListing] = []
        while True:
            payload = {"limit": limit, "offset": offset}
            if country_ids:
                payload["appliedFacets"] = {"locationHierarchy1": country_ids}
            data = post_json(endpoint, payload)
            job_postings = data.get("jobPostings", [])
            if not job_postings:
                break
            for item in job_postings:
                job_id = item.get("bulletFields", [""])[0] or item["externalPath"].rsplit("_", 1)[-1]
                listings.append(
                    SourceListing(
                        external_id=job_id,
                        title=item["title"],
                        url=self.source_config["careers_url"].rstrip("/") + item["externalPath"],
                        location_text=item.get("locationsText", ""),
                        metadata=item,
                    )
                )
            offset += limit
            if offset >= int(data.get("total", 0)):
                break
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
        location_text = item.get("locationsText", "")
        country = detect_country(location_text, default=self.source_config.get("country"))
        posted_at = _parse_relative_date(item.get("postedOn"))
        job_code = item.get("bulletFields", [""])

        return NormalizedJob(
            source_name=payload.source_name,
            source_job_id=payload.source_job_id,
            canonical_url=payload.canonical_url,
            company=self.source_config["company_name"],
            title=item.get("title", ""),
            location_text=location_text,
            country=Country(country or self.source_config["country"]),
            location_country_code=country,
            posted_at=posted_at,
            description_text=f"{item.get('title', '')} {location_text}".strip(),
            requirements_text=" ".join(job_code),
            seniority=None,
            employer_class=EmployerClass(self.source_config["employer_class"]),
            language_signals=["en"],
        )


def _country_facet_ids(payload: dict, target_names: list[str]) -> list[str]:
    for facet in payload.get("facets", []):
        if facet.get("facetParameter") != "locationMainGroup":
            continue
        for inner in facet.get("values", []):
            if inner.get("facetParameter") != "locationHierarchy1":
                continue
            matches = []
            for value in inner.get("values", []):
                if value.get("descriptor") in target_names:
                    matches.append(value["id"])
            return matches
    return []


def _parse_relative_date(value: str | None) -> datetime | None:
    if not value:
        return None
    return None
