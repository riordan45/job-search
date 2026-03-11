from __future__ import annotations

from datetime import datetime
from html import unescape
import json
import re
import xml.etree.ElementTree as ET

from job_search.adapters.base import SourceAdapter
from job_search.adapters.http import fetch_text
from job_search.enums import Country, EmployerClass
from job_search.models import NormalizedJob, RawJobPayload, SourceListing
from job_search.scoring import detect_country, infer_remote_mode


SITEMAP_URL = "https://www.asml.com/en/job_posting-sitemap.xml"
NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)
TARGET_COUNTRIES = {"germany", "the netherlands", "netherlands", "romania", "switzerland"}


class AsmlJobsAdapter(SourceAdapter):
    def discover_openings(self) -> list[SourceListing]:
        xml = fetch_text(SITEMAP_URL)
        listings: list[SourceListing] = []
        for url in _extract_sitemap_urls(xml):
            job = _extract_job_payload(fetch_text(url))
            if not _is_target_country(str(job.get("country", ""))):
                continue
            external_id = str(job.get("id") or _job_id_from_url(url))
            title = _clean_text(job.get("displayJobTitle", ""))
            location_text = _location_text(job)
            listings.append(
                SourceListing(
                    external_id=external_id,
                    title=title,
                    url=str(job.get("detailPageUrl") or url),
                    location_text=location_text,
                    posted_at=_parse_datetime(job.get("datePosted")),
                    metadata=job,
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
        job = payload.payload
        location_text = _location_text(job)
        country = detect_country(location_text, default=self.source_config.get("country"))
        description = _clean_html(job.get("descriptionExternal", ""))
        remote_mode = _remote_mode(job, description, location_text)

        return NormalizedJob(
            source_name=payload.source_name,
            source_job_id=payload.source_job_id,
            canonical_url=payload.canonical_url,
            company=self.source_config["company_name"],
            title=_clean_text(job.get("displayJobTitle", "")),
            location_text=location_text,
            country=Country(country or self.source_config["country"]),
            location_country_code=country,
            employment_type=_employment_type(job),
            remote_mode=remote_mode,
            posted_at=_parse_datetime(job.get("datePosted")),
            description_text=description,
            requirements_text=description,
            seniority=_infer_seniority(job.get("displayJobTitle", "")),
            employer_class=EmployerClass(self.source_config["employer_class"]),
            language_signals=["en"],
        )


def _extract_sitemap_urls(xml: str) -> list[str]:
    namespace = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    root = ET.fromstring(xml)
    return [
        element.text.strip()
        for element in root.findall("sm:url/sm:loc", namespace)
        if element.text and "/en/careers/find-your-job/" in element.text
    ]


def _extract_job_payload(html: str) -> dict:
    match = NEXT_DATA_RE.search(html)
    if not match:
        raise ValueError("ASML job payload not found")
    payload = json.loads(match.group(1))
    return payload["props"]["pageProps"]["jobData"]


def _is_target_country(country: str) -> bool:
    return _clean_text(country).lower() in TARGET_COUNTRIES


def _job_id_from_url(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1]


def _location_text(job: dict) -> str:
    location = _clean_text(job.get("location", ""))
    if location:
        return location
    city = _clean_text(job.get("city", ""))
    country = _clean_text(job.get("country", ""))
    return ", ".join(part for part in [city, country] if part)


def _employment_type(job: dict) -> str | None:
    parts = [_clean_text(job.get("timeType", "")), _clean_text(job.get("jobType", ""))]
    value = " | ".join(part for part in parts if part)
    return value or None


def _remote_mode(job: dict, description: str, location_text: str) -> str | None:
    remote_work = _clean_text(job.get("remoteWork", "")).lower()
    if remote_work:
        if "hybrid" in remote_work:
            return "hybrid"
        if "remote" in remote_work:
            return "remote"
        if "site" in remote_work or "office" in remote_work:
            return "onsite"
    return infer_remote_mode(" ".join([location_text, description]))


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def _clean_html(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", str(value))
    return _clean_text(without_tags)


def _clean_text(value: str) -> str:
    return " ".join(unescape(str(value)).replace("\xa0", " ").split())


def _infer_seniority(title: str) -> str | None:
    lowered = title.lower()
    for candidate in ["staff", "senior", "lead", "principal", "manager", "intern"]:
        if candidate in lowered:
            return candidate
    return None
