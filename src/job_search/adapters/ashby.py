from __future__ import annotations

from datetime import datetime

from job_search.adapters.base import SourceAdapter
from job_search.adapters.http import post_json
from job_search.enums import Country, EmployerClass
from job_search.models import NormalizedJob, RawJobPayload, SourceListing
from job_search.scoring import detect_country, infer_remote_mode


class AshbyAdapter(SourceAdapter):
    def discover_openings(self) -> list[SourceListing]:
        job_board_name = self.source_config["job_board_name"]
        payload = {
            "jobBoardName": job_board_name,
            "includeCompensation": False,
        }
        data = post_json("https://jobs.ashbyhq.com/api/non-user-job-posting-api", payload)
        listings: list[SourceListing] = []
        for item in data.get("jobs", []):
            location_text = _location_text(item)
            listings.append(
                SourceListing(
                    external_id=item["id"],
                    title=item.get("title", ""),
                    url=_job_posting_url(job_board_name, item["id"]),
                    location_text=location_text,
                    posted_at=_parse_datetime(item.get("publishedDate")),
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
        location_text = _location_text(item)
        text_parts = [item.get("title", ""), location_text, item.get("descriptionPlain", "")]
        country = detect_country(" ".join(part for part in text_parts if part), default=self.source_config.get("country"))

        return NormalizedJob(
            source_name=payload.source_name,
            source_job_id=payload.source_job_id,
            canonical_url=payload.canonical_url,
            company=self.source_config["company_name"],
            title=item.get("title", ""),
            location_text=location_text,
            country=Country(country or self.source_config["country"]),
            location_country_code=country,
            employment_type=item.get("employmentType"),
            remote_mode=infer_remote_mode(" ".join(text_parts)),
            posted_at=_parse_datetime(item.get("publishedDate")),
            description_text=item.get("descriptionPlain", ""),
            requirements_text=item.get("jobSummary", ""),
            seniority=_infer_seniority(item.get("title", "")),
            employer_class=EmployerClass(self.source_config["employer_class"]),
            language_signals=["en"],
        )


def _job_posting_url(job_board_name: str, job_id: str) -> str:
    return f"https://jobs.ashbyhq.com/{job_board_name}/job/{job_id}"


def _location_text(item: dict) -> str:
    location = item.get("location") or ""
    location_name = str(location).strip()
    workplace = str(item.get("workplace") or "").strip()
    if location_name and workplace and workplace.lower() not in location_name.lower():
        return f"{location_name} · {workplace}"
    return location_name or workplace


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _infer_seniority(title: str) -> str | None:
    lowered = title.lower()
    for candidate in ["principal", "staff", "senior", "lead", "manager", "director"]:
        if candidate in lowered:
            return candidate
    return None
