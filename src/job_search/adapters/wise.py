from __future__ import annotations

from datetime import datetime
from html import unescape
import json
import re

from job_search.adapters.base import SourceAdapter
from job_search.adapters.http import fetch_text
from job_search.enums import Country, EmployerClass
from job_search.models import NormalizedJob, RawJobPayload, SourceListing
from job_search.scoring import detect_country, infer_remote_mode


JOB_LINK_RE = re.compile(r'href="(/job/[^"]+)"', re.I)
JSON_LD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S | re.I)


class WiseJobsAdapter(SourceAdapter):
    def discover_openings(self) -> list[SourceListing]:
        html = fetch_text(self.source_config["careers_url"])
        listings: list[SourceListing] = []
        seen_urls: set[str] = set()
        for path in JOB_LINK_RE.findall(html):
            url = _absolute_url(path)
            if url in seen_urls:
                continue
            seen_urls.add(url)
            title = _title_from_path(path)
            location_text = _location_from_path(path)
            country_code = detect_country(" ".join([title, location_text]))
            if not country_code:
                continue
            listings.append(
                SourceListing(
                    external_id=path.rsplit("-jid-", 1)[-1],
                    title=title,
                    url=url,
                    location_text=location_text,
                    metadata={"country_code": country_code},
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
                "country_code": listing.metadata.get("country_code"),
            },
        )

    def normalize(self, payload: RawJobPayload) -> NormalizedJob:
        html = payload.payload["html"]
        posting = _extract_job_posting(html)
        title = posting.get("title") or _extract_title(html)
        location_text = _location_text(posting)
        country_code = (
            detect_country(" ".join([title, location_text]))
            or payload.payload.get("country_code")
            or self.source_config.get("country")
        )
        description_html = posting.get("description", "")
        description_text = _clean_html(description_html)

        return NormalizedJob(
            source_name=payload.source_name,
            source_job_id=payload.source_job_id,
            canonical_url=payload.canonical_url,
            company=self.source_config["company_name"],
            title=title,
            location_text=location_text,
            country=Country(country_code or self.source_config["country"]),
            location_country_code=country_code,
            employment_type=_employment_type(posting.get("employmentType")),
            remote_mode=infer_remote_mode(" ".join([title, location_text, description_text])),
            posted_at=_parse_datetime(posting.get("datePosted")),
            description_text=description_text or title,
            requirements_text="",
            seniority=_infer_seniority(title),
            employer_class=EmployerClass(self.source_config["employer_class"]),
            language_signals=["en"],
        )


def _absolute_url(path: str) -> str:
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return f"https://www.wise.jobs{path}"


def _title_from_path(path: str) -> str:
    slug = path.rsplit("/", 1)[-1]
    slug = slug.rsplit("-jid-", 1)[0]
    slug = re.sub(r"-in-[a-z0-9-]+$", "", slug)
    return " ".join(part.capitalize() for part in slug.split("-"))


def _location_from_path(path: str) -> str:
    slug = path.rsplit("/", 1)[-1]
    match = re.search(r"-in-([a-z0-9-]+)-jid-", slug)
    if not match:
        return ""
    return " ".join(part.capitalize() for part in match.group(1).split("-"))


def _extract_job_posting(html: str) -> dict:
    for raw in JSON_LD_RE.findall(html):
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if payload.get("@type") == "JobPosting":
            return payload
    return {}


def _extract_title(html: str) -> str:
    match = re.search(r"<title>\s*(.*?)\s+job in .*?\|\s*Wise\s*</title>", html, re.S | re.I)
    if not match:
        return ""
    return _clean_text(match.group(1))


def _location_text(posting: dict) -> str:
    locations = posting.get("jobLocation") or []
    if not isinstance(locations, list):
        return ""
    values: list[str] = []
    for item in locations:
        locality = (
            item.get("address", {}).get("addressLocality")
            if isinstance(item, dict)
            else None
        )
        if locality and locality not in values:
            values.append(str(locality))
    return " | ".join(values)


def _employment_type(value: object) -> str | None:
    if isinstance(value, list):
        joined = ", ".join(str(item) for item in value if item)
        return joined or None
    if isinstance(value, str):
        return value or None
    return None


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _clean_text(value: str) -> str:
    return " ".join(unescape(value).replace("\xa0", " ").split())


def _clean_html(value: str) -> str:
    if not value:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    text = re.sub(r"</p\s*>", "\n\n", text, flags=re.I)
    text = re.sub(r"<li[^>]*>", "- ", text, flags=re.I)
    text = re.sub(r"</li>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return _clean_text(text)


def _infer_seniority(title: str) -> str | None:
    lowered = title.lower()
    for candidate in ["principal", "staff", "senior", "lead", "manager", "director"]:
        if candidate in lowered:
            return candidate
    return None
