from __future__ import annotations

from datetime import datetime
from html import unescape
import re
from urllib.parse import quote_plus

from job_search.adapters.base import SourceAdapter
from job_search.adapters.http import fetch_text
from job_search.enums import Country, EmployerClass
from job_search.models import NormalizedJob, RawJobPayload, SourceListing
from job_search.scoring import detect_country, infer_remote_mode


JOB_LINK_RE = re.compile(
    r'href="(?P<url>/v2/global/en/job/(?P<id>[^"/]+)/[^"]+)"[^>]*>\s*<h3[^>]*>(?P<title>.*?)</h3>(?P<body>.*?)</a>',
    re.S | re.I,
)


class MicrosoftCareersAdapter(SourceAdapter):
    def discover_openings(self) -> list[SourceListing]:
        listings: list[SourceListing] = []
        seen_ids: set[str] = set()
        for location_slug in self.source_config.get("search_locations", []):
            html = fetch_text(_location_url(location_slug))
            for item in _extract_listings(html):
                if item["external_id"] in seen_ids:
                    continue
                seen_ids.add(item["external_id"])
                listings.append(
                    SourceListing(
                        external_id=item["external_id"],
                        title=item["title"],
                        url=item["url"],
                        location_text=item["location_text"],
                        posted_at=item["posted_at"],
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
        location_text = item["location_text"]
        country = detect_country(location_text, default=self.source_config.get("country"))
        description_parts = [item.get("work_site", ""), item.get("profession", "")]
        description_text = "\n".join(part for part in description_parts if part)

        return NormalizedJob(
            source_name=payload.source_name,
            source_job_id=payload.source_job_id,
            canonical_url=payload.canonical_url,
            company=self.source_config["company_name"],
            title=item["title"],
            location_text=location_text,
            country=Country(country or self.source_config["country"]),
            location_country_code=country,
            remote_mode=infer_remote_mode(" ".join([item["title"], location_text, description_text])),
            posted_at=item.get("posted_at"),
            description_text=description_text or item["title"],
            requirements_text=item.get("profession", ""),
            seniority=_infer_seniority(item["title"]),
            employer_class=EmployerClass(self.source_config["employer_class"]),
            language_signals=["en"],
        )


def _location_url(location_slug: str) -> str:
    return f"https://careers.microsoft.com/v2/global/en/locations/{quote_plus(location_slug)}.html"


def _extract_listings(html: str) -> list[dict]:
    listings: list[dict] = []
    for match in JOB_LINK_RE.finditer(html):
        body = match.group("body")
        location_text = _extract_field(body, "Location")
        if not detect_country(location_text):
            continue
        listings.append(
            {
                "external_id": match.group("id"),
                "title": _clean_text(match.group("title")),
                "url": _absolute_url(match.group("url")),
                "location_text": location_text,
                "profession": _extract_field(body, "Profession"),
                "work_site": _extract_field(body, "Work site"),
                "posted_at": _parse_datetime(_extract_field(body, "Date posted")),
            }
        )
    return listings


def _extract_field(body: str, label: str) -> str:
    match = re.search(
        rf"{re.escape(label)}\s*</span>\s*<span[^>]*>(.*?)</span>",
        body,
        re.S | re.I,
    )
    return _clean_text(match.group(1)) if match else ""


def _absolute_url(path: str) -> str:
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return f"https://careers.microsoft.com{path}"


def _parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    for fmt in ("%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _clean_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    return " ".join(unescape(text).replace("\xa0", " ").split())


def _infer_seniority(title: str) -> str | None:
    lowered = title.lower()
    for candidate in ["principal", "staff", "senior", "lead", "manager"]:
        if candidate in lowered:
            return candidate
    return None
