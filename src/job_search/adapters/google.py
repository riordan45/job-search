from __future__ import annotations

from datetime import datetime
from html import unescape
import re
from urllib.parse import quote_plus

from job_search.adapters.base import SourceAdapter
from job_search.adapters.http import fetch_text
from job_search.enums import Country, EmployerClass
from job_search.models import NormalizedJob, RawJobPayload, SourceListing
from job_search.scoring import detect_country


RESULT_URL_RE = re.compile(r"jobs/results/(\d+[-a-z0-9]+)(?:\?[^\"'<\s]+)?", re.I)


class GoogleCareersAdapter(SourceAdapter):
    def discover_openings(self) -> list[SourceListing]:
        listings: list[SourceListing] = []
        seen_ids: set[str] = set()
        max_pages = int(self.source_config.get("max_pages", 3))
        query = self.source_config.get("query", "")
        for location in self.source_config.get("search_locations", []):
            for page in range(1, max_pages + 1):
                html = fetch_text(_search_url(location=location, query=query, page=page))
                matches = RESULT_URL_RE.findall(html)
                if not matches:
                    break
                found_new = False
                for slug in matches:
                    job_id = slug.split("-", 1)[0]
                    if job_id in seen_ids:
                        continue
                    seen_ids.add(job_id)
                    found_new = True
                    listings.append(
                        SourceListing(
                            external_id=job_id,
                            title=slug,
                            url=_detail_url(slug, location),
                            location_text=location,
                            metadata={"slug": slug, "search_location": location},
                        )
                    )
                if not found_new:
                    break
        return listings

    def fetch_job(self, listing: SourceListing) -> RawJobPayload:
        html = fetch_text(listing.url)
        return RawJobPayload(
            source_name=self.source_config["name"],
            source_job_id=listing.external_id,
            canonical_url=listing.url,
            payload={
                "html": html,
                "slug": listing.metadata["slug"],
                "search_location": listing.metadata["search_location"],
            },
        )

    def normalize(self, payload: RawJobPayload) -> NormalizedJob:
        html = payload.payload["html"]
        search_location = payload.payload["search_location"]
        title = _extract_title(html, payload.payload["slug"])
        about = _extract_section(html, "About the job")
        minimum = _extract_list_section(html, "Minimum qualifications:")
        preferred = _extract_list_section(html, "Preferred qualifications:")
        responsibilities = _extract_list_section(html, "Responsibilities")
        description_parts = [about, responsibilities]
        requirements_parts = [minimum, preferred]
        country = detect_country(search_location, default=self.source_config.get("country"))

        return NormalizedJob(
            source_name=payload.source_name,
            source_job_id=payload.source_job_id,
            canonical_url=payload.canonical_url,
            company=self.source_config["company_name"],
            title=title,
            location_text=search_location,
            country=Country(country or self.source_config["country"]),
            location_country_code=country,
            posted_at=None,
            description_text="\n\n".join(part for part in description_parts if part),
            requirements_text="\n\n".join(part for part in requirements_parts if part),
            seniority=_infer_seniority(title),
            employer_class=EmployerClass(self.source_config["employer_class"]),
            language_signals=["en"],
        )


def _search_url(*, location: str, query: str, page: int) -> str:
    base = "https://www.google.com/about/careers/applications/jobs/results/"
    params = [f"location={quote_plus(location)}", f"page={page}"]
    if query:
        params.insert(0, f"q={quote_plus(query)}")
    return f"{base}?{'&'.join(params)}"


def _detail_url(slug: str, location: str) -> str:
    return (
        "https://www.google.com/about/careers/applications/jobs/results/"
        f"{slug}?location={quote_plus(location)}"
    )


def _extract_title(html: str, fallback_slug: str) -> str:
    match = re.search(r"<title>(.*?)\s+[—-]\s+Google Careers</title>", html, re.S | re.I)
    if match:
        return _clean_text(match.group(1))
    slug = fallback_slug.split("-", 1)[1] if "-" in fallback_slug else fallback_slug
    return _clean_text(slug.replace("-", " "))


def _extract_section(html: str, heading: str) -> str:
    pattern = re.compile(
        rf"<h3>\s*{re.escape(heading)}\s*</h3>(.*?)(?:<div class=\"[^\"]+\"><h3>|</div><div class=\"[^\"]+\"><h3>|<div class=\"bE3reb\">)",
        re.S | re.I,
    )
    match = pattern.search(html)
    if not match:
        return ""
    return _clean_text(_strip_tags(match.group(1)))


def _extract_list_section(html: str, heading: str) -> str:
    pattern = re.compile(
        rf"<h3>\s*{re.escape(heading)}\s*</h3>\s*<ul>(.*?)</ul>",
        re.S | re.I,
    )
    match = pattern.search(html)
    if not match:
        return ""
    items = re.findall(r"<li>(.*?)</li>", match.group(1), re.S | re.I)
    return "\n".join(f"- {_clean_text(_strip_tags(item))}" for item in items if _clean_text(_strip_tags(item)))


def _strip_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", value)


def _clean_text(value: str) -> str:
    return " ".join(unescape(value).replace("\xa0", " ").split())


def _infer_seniority(title: str) -> str | None:
    lowered = title.lower()
    for candidate in ["staff", "senior", "lead", "principal", "manager"]:
        if candidate in lowered:
            return candidate
    return None
