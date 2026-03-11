from __future__ import annotations

from html import unescape
import re

from job_search.adapters.base import SourceAdapter
from job_search.adapters.http import fetch_json
from job_search.enums import Country, EmployerClass
from job_search.models import NormalizedJob, RawJobPayload, SourceListing
from job_search.scoring import infer_remote_mode


MAIN_JOBS_URL = "https://www.janestreet.com/jobs/main.json"
POSITION_DIRECTORIES_URL = "https://www.janestreet.com/static/position-directories.json"
DETAIL_URL_TEMPLATE = "https://www.janestreet.com/join-jane-street/position/{job_id}/"
TARGET_CITY_NAMES = {"AMS": "Amsterdam, Netherlands"}


class JaneStreetJobsAdapter(SourceAdapter):
    def discover_openings(self) -> list[SourceListing]:
        listings: list[SourceListing] = []
        allowed_ids = {str(job_id) for job_id in fetch_json(POSITION_DIRECTORIES_URL)}
        for item in fetch_json(MAIN_JOBS_URL):
            external_id = str(item["id"])
            if external_id not in allowed_ids:
                continue
            location_text = _location_text(item)
            if not location_text:
                continue
            listings.append(
                SourceListing(
                    external_id=external_id,
                    title=item.get("position", ""),
                    url=_detail_url(external_id),
                    location_text=location_text,
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
        overview = _clean_html(item.get("overview", ""))
        location_text = _location_text(item)
        return NormalizedJob(
            source_name=payload.source_name,
            source_job_id=payload.source_job_id,
            canonical_url=payload.canonical_url,
            company=self.source_config["company_name"],
            title=item.get("position", ""),
            location_text=location_text,
            country=Country(self.source_config["country"]),
            location_country_code="NL",
            employment_type=item.get("availability"),
            remote_mode=infer_remote_mode(overview),
            posted_at=None,
            description_text=overview,
            requirements_text=overview,
            seniority=_infer_seniority(item.get("position", "")),
            employer_class=EmployerClass(self.source_config["employer_class"]),
            language_signals=["en"],
        )


def _detail_url(job_id: str) -> str:
    return DETAIL_URL_TEMPLATE.format(job_id=job_id)


def _location_text(item: dict) -> str:
    return TARGET_CITY_NAMES.get(str(item.get("city", "")).strip(), "")


def _clean_html(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", value)
    return " ".join(unescape(without_tags).replace("\xa0", " ").split())


def _infer_seniority(title: str) -> str | None:
    lowered = title.lower()
    for candidate in ["staff", "senior", "lead", "principal", "manager", "intern"]:
        if candidate in lowered:
            return candidate
    return None
