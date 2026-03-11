from __future__ import annotations

from datetime import datetime
import html
import json
import re
from urllib.parse import quote

from job_search.adapters.base import SourceAdapter
from job_search.adapters.http import fetch_text
from job_search.enums import Country, EmployerClass
from job_search.models import NormalizedJob, RawJobPayload, SourceListing
from job_search.scoring import detect_country, infer_remote_mode


DATA_RE = re.compile(r'28:\{"data":(\[.*?\]),"total":', re.S)


class ZalandoJobsAdapter(SourceAdapter):
    def discover_openings(self) -> list[SourceListing]:
        html_text = fetch_text(self.source_config["jobs_url"])
        jobs = _extract_jobs(html_text)
        listings: list[SourceListing] = []
        for item in jobs:
            location_text = " | ".join(item.get("offices", []))
            country_code = detect_country(location_text)
            if not country_code:
                continue
            listings.append(
                SourceListing(
                    external_id=str(item["id"]),
                    title=item.get("title", ""),
                    url=_job_url(str(item["id"]), item.get("title", "")),
                    location_text=location_text,
                    posted_at=_parse_datetime(item.get("updated_at")),
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
        location_text = " | ".join(item.get("offices", []))
        country_code = detect_country(location_text, default=self.source_config.get("country"))
        title = item.get("title", "")
        categories = item.get("job_categories", [])
        description_text = "\n".join(
            part for part in [item.get("entity", ""), ", ".join(categories), item.get("experience_level", "")] if part
        )
        return NormalizedJob(
            source_name=payload.source_name,
            source_job_id=payload.source_job_id,
            canonical_url=payload.canonical_url,
            company=self.source_config["company_name"],
            title=title,
            location_text=location_text,
            country=Country(country_code or self.source_config["country"]),
            location_country_code=country_code,
            remote_mode=infer_remote_mode(" ".join([title, location_text, description_text])),
            posted_at=_parse_datetime(item.get("updated_at")),
            description_text=description_text or title,
            requirements_text=", ".join(categories),
            seniority=_infer_seniority(title),
            employer_class=EmployerClass(self.source_config["employer_class"]),
            language_signals=["en"],
        )


def _extract_jobs(html_text: str) -> list[dict]:
    match = DATA_RE.search(html_text)
    if not match:
        return []
    return json.loads(html.unescape(match.group(1)))


def _job_url(job_id: str, title: str) -> str:
    slug = quote(title.replace(" ", "-"), safe="-()")
    return f"https://jobs.zalando.com/en/jobs/{job_id}-{slug}"


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def _infer_seniority(title: str) -> str | None:
    lowered = title.lower()
    for candidate in ["principal", "staff", "senior", "lead", "manager"]:
        if candidate in lowered:
            return candidate
    return None
