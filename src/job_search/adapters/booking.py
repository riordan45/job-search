from __future__ import annotations

from datetime import datetime
from html import unescape
from urllib.parse import urlencode, urlsplit

from job_search.adapters.base import SourceAdapter
from job_search.adapters.http import fetch_json
from job_search.enums import Country, EmployerClass
from job_search.models import NormalizedJob, RawJobPayload, SourceListing
from job_search.scoring import detect_country, infer_remote_mode


class BookingJobsAdapter(SourceAdapter):
    def discover_openings(self) -> list[SourceListing]:
        careers_url = self.source_config["careers_url"]
        page_size = int(self.source_config.get("page_size", 10))
        max_pages = int(self.source_config.get("max_pages", 5))
        search_locations = self.source_config.get("search_locations", [])
        seen_ids: set[str] = set()
        listings: list[SourceListing] = []

        for location in search_locations:
            for page in range(1, max_pages + 1):
                response = fetch_json(_search_url(careers_url, location, page=page, limit=page_size))
                jobs = response.get("jobs", [])
                if not jobs:
                    break
                for item in jobs:
                    data = item.get("data", {})
                    external_id = str(data.get("req_id") or data.get("slug") or "")
                    if not external_id or external_id in seen_ids:
                        continue
                    listing_location = _location_text(data)
                    country_code = detect_country(listing_location)
                    if not country_code:
                        continue
                    seen_ids.add(external_id)
                    listings.append(
                        SourceListing(
                            external_id=external_id,
                            title=data.get("title", ""),
                            url=_canonical_url(data),
                            location_text=listing_location,
                            posted_at=_parse_datetime(data.get("posted_date")),
                            metadata=data,
                        )
                    )
                if len(jobs) < page_size:
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
        title = item.get("title", "")
        location_text = _location_text(item)
        description_text = _clean_text(item.get("description", ""))
        requirements_text = ", ".join(_category_names(item))
        country_code = detect_country(location_text, default=self.source_config.get("country"))

        return NormalizedJob(
            source_name=payload.source_name,
            source_job_id=payload.source_job_id,
            canonical_url=payload.canonical_url,
            company=self.source_config["company_name"],
            title=title,
            location_text=location_text,
            country=Country(country_code or self.source_config["country"]),
            location_country_code=country_code,
            employment_type=item.get("employment_type"),
            remote_mode=infer_remote_mode(" ".join([title, location_text, description_text])),
            posted_at=_parse_datetime(item.get("posted_date")),
            description_text=description_text or title,
            requirements_text=requirements_text,
            seniority=_infer_seniority(title),
            employer_class=EmployerClass(self.source_config["employer_class"]),
            language_signals=["en"],
        )


def _search_url(careers_url: str, location: str, *, page: int, limit: int) -> str:
    params = {"location": location, "page": str(page), "limit": str(limit)}
    return f"{_origin(careers_url)}/api/jobs?{urlencode(params)}"


def _origin(careers_url: str) -> str:
    parsed = urlsplit(careers_url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _canonical_url(item: dict) -> str:
    meta_data = item.get("meta_data") if isinstance(item.get("meta_data"), dict) else {}
    canonical = meta_data.get("canonical_url")
    if canonical:
        return str(canonical)
    apply_url = item.get("apply_url")
    if apply_url:
        return str(apply_url)
    req_id = item.get("req_id") or item.get("slug")
    return f"https://jobs.booking.com/booking/jobs/{req_id}?lang=en-us"


def _location_text(item: dict) -> str:
    for key in ("full_location", "short_location"):
        value = item.get(key)
        if value:
            return str(value)
    values = [item.get("city"), item.get("state"), item.get("country")]
    return ", ".join(str(value) for value in values if value)


def _category_names(item: dict) -> list[str]:
    categories = item.get("categories") or []
    names: list[str] = []
    for category in categories:
        if isinstance(category, dict):
            name = category.get("name")
            if name:
                names.append(str(name))
        elif category:
            names.append(str(category))
    return names


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S%z")


def _clean_text(value: str) -> str:
    return " ".join(unescape(value).replace("\xa0", " ").split())


def _infer_seniority(title: str) -> str | None:
    lowered = title.lower()
    for candidate in ["principal", "staff", "senior", "lead", "manager", "director"]:
        if candidate in lowered:
            return candidate
    return None
