from __future__ import annotations

from datetime import datetime
from html import unescape
import json
import re

from job_search.adapters.base import SourceAdapter
from job_search.adapters.http import fetch_json, fetch_text
from job_search.enums import Country, EmployerClass
from job_search.models import NormalizedJob, RawJobPayload, SourceListing
from job_search.scoring import detect_country, infer_remote_mode


SEARCH_URL = "https://api.lifeatspotify.com/wp-json/animal/v1/job/search"
DETAIL_URL_TEMPLATE = "https://www.lifeatspotify.com/jobs/{job_id}"
NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)
TARGET_LOCATION_SLUGS = {
    "amsterdam": "NL",
    "berlin": "DE",
    "dusseldorf": "DE",
    "hamburg": "DE",
    "munich": "DE",
}


class SpotifyJobsAdapter(SourceAdapter):
    def discover_openings(self) -> list[SourceListing]:
        data = fetch_json(SEARCH_URL)
        listings: list[SourceListing] = []
        for item in data.get("result", []):
            target_locations = _target_locations(item)
            if not target_locations:
                continue
            listings.append(
                SourceListing(
                    external_id=item["id"],
                    title=_clean_text(item.get("text", "")),
                    url=_detail_url(item["id"]),
                    location_text=" | ".join(target_locations),
                    metadata=item,
                )
            )
        return listings

    def fetch_job(self, listing: SourceListing) -> RawJobPayload:
        html = fetch_text(listing.url)
        return RawJobPayload(
            source_name=self.source_config["name"],
            source_job_id=listing.external_id,
            canonical_url=listing.url,
            payload={
                "html": html,
                "listing": listing.model_dump(),
            },
        )

    def normalize(self, payload: RawJobPayload) -> NormalizedJob:
        job = _extract_job_payload(payload.payload["html"])
        listing = payload.payload["listing"]
        location_names = job.get("categories", {}).get("locations") or [job.get("categories", {}).get("location", "")]
        location_text = " | ".join(
            location for location in location_names if _country_for_location_name(location)
        ) or listing.get("location_text", "")
        country = _country_for_location_name(location_text.split(" | ", 1)[0]) or detect_country(
            location_text,
            default=self.source_config.get("country"),
        )
        content = job.get("content", {})
        description = _section_text(content.get("descriptionHtml", "")) or _clean_text(content.get("description", ""))
        closing = _section_text(content.get("closingHtml", ""))
        requirements = _requirements_text(content.get("lists", []))
        full_text = " ".join(
            [job.get("text", ""), location_text, description, closing, requirements]
        )

        return NormalizedJob(
            source_name=payload.source_name,
            source_job_id=payload.source_job_id,
            canonical_url=payload.canonical_url,
            company=self.source_config["company_name"],
            title=_clean_text(job.get("text", listing.get("title", ""))),
            location_text=location_text,
            country=Country(country or self.source_config["country"]),
            location_country_code=country,
            employment_type=job.get("categories", {}).get("commitment"),
            remote_mode=infer_remote_mode(full_text),
            posted_at=_parse_epoch(job.get("createdAt")),
            description_text="\n\n".join(part for part in [description, closing] if part),
            requirements_text=requirements,
            seniority=_infer_seniority(job.get("text", listing.get("title", ""))),
            employer_class=EmployerClass(self.source_config["employer_class"]),
            language_signals=["en"],
        )


def _detail_url(job_id: str) -> str:
    return DETAIL_URL_TEMPLATE.format(job_id=job_id)


def _target_locations(item: dict) -> list[str]:
    return [
        str(location.get("location", "")).strip()
        for location in item.get("locations", [])
        if str(location.get("slug", "")) in TARGET_LOCATION_SLUGS
    ]


def _extract_job_payload(html: str) -> dict:
    match = NEXT_DATA_RE.search(html)
    if not match:
        raise ValueError("Spotify job payload not found")
    payload = json.loads(match.group(1))
    return payload["props"]["pageProps"]["job"]


def _parse_epoch(value: int | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value / 1000)


def _country_for_location_name(location: str) -> str | None:
    normalized = _clean_text(location).lower()
    if normalized in {"dusseldorf", "düsseldorf"}:
        return "DE"
    return detect_country(location)


def _section_text(html: str) -> str:
    return _clean_text(re.sub(r"<[^>]+>", " ", html))


def _requirements_text(lists: list[dict]) -> str:
    parts: list[str] = []
    for item in lists:
        heading = _clean_text(item.get("text", ""))
        body = _section_text(item.get("content", ""))
        if heading and body:
            parts.append(f"{heading}: {body}")
        elif body:
            parts.append(body)
    return "\n\n".join(parts)


def _clean_text(value: str) -> str:
    return " ".join(unescape(str(value)).replace("\xa0", " ").split())


def _infer_seniority(title: str) -> str | None:
    lowered = title.lower()
    for candidate in ["staff", "senior", "lead", "principal", "manager"]:
        if candidate in lowered:
            return candidate
    return None
