from __future__ import annotations

from datetime import datetime

from job_search.adapters.base import SourceAdapter
from job_search.adapters.http import fetch_json
from job_search.enums import Country, EmployerClass
from job_search.models import NormalizedJob, RawJobPayload, SourceListing
from job_search.scoring import detect_country, infer_remote_mode


class SmartRecruitersAdapter(SourceAdapter):
    def discover_openings(self) -> list[SourceListing]:
        identifier = self.source_config["company_identifier"]
        limit = int(self.source_config.get("limit", 100))
        offset = 0
        listings: list[SourceListing] = []
        while True:
            data = fetch_json(
                f"https://api.smartrecruiters.com/v1/companies/{identifier}/postings?limit={limit}&offset={offset}"
            )
            content = data.get("content", [])
            for item in content:
                listings.append(
                    SourceListing(
                        external_id=item["id"],
                        title=item["name"],
                        url=item.get("ref", ""),
                        location_text=item.get("location", {}).get("fullLocation", ""),
                        metadata=item,
                    )
                )
            offset += limit
            if offset >= int(data.get("totalFound", 0)) or not content:
                break
        return listings

    def fetch_job(self, listing: SourceListing) -> RawJobPayload:
        payload = listing.metadata
        ref = payload.get("ref")
        if ref:
            try:
                payload = fetch_json(ref)
            except Exception:  # noqa: BLE001
                payload = listing.metadata
        return RawJobPayload(
            source_name=self.source_config["name"],
            source_job_id=listing.external_id,
            canonical_url=payload.get("applyUrl") or payload.get("postingUrl") or payload.get("ref") or listing.url,
            payload=payload,
        )

    def normalize(self, payload: RawJobPayload) -> NormalizedJob:
        item = payload.payload
        location = item.get("location", {})
        full_location = location.get("fullLocation") or location.get("city") or ""
        description = item.get("jobAd", {}).get("sections", {}).get("jobDescription", {}).get("text", "")
        qualifications = item.get("jobAd", {}).get("sections", {}).get("qualifications", {}).get("text", "")
        text = " ".join([item.get("name", ""), description, qualifications, full_location])
        country = detect_country(
            f'{full_location} {location.get("country", "")}',
            default=self.source_config.get("country"),
        )
        return NormalizedJob(
            source_name=payload.source_name,
            source_job_id=payload.source_job_id,
            canonical_url=payload.canonical_url,
            company=self.source_config["company_name"],
            title=item.get("name", ""),
            location_text=full_location,
            country=Country(country or self.source_config["country"]),
            location_country_code=str(location.get("country", "")).upper() or None,
            employment_type=item.get("typeOfEmployment", {}).get("label"),
            remote_mode=infer_remote_mode(text),
            posted_at=_parse_datetime(item.get("releasedDate")),
            description_text=description,
            requirements_text=qualifications,
            seniority=item.get("experienceLevel", {}).get("label"),
            employer_class=EmployerClass(self.source_config["employer_class"]),
            language_signals=[item.get("language", {}).get("code", "en")],
        )


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
