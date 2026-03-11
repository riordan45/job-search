from __future__ import annotations

from datetime import datetime
from html import unescape
import json
import re

import cloudscraper

from job_search.adapters.base import SourceAdapter
from job_search.enums import Country, EmployerClass
from job_search.models import NormalizedJob, RawJobPayload, SourceListing
from job_search.scoring import detect_country, infer_remote_mode


DEFAULT_QUERIES = [
    "software",
    "machine learning",
    "applied scientist",
    "data scientist",
]
DEFAULT_TARGET_COUNTRY_CODES = ["CHE", "DEU", "NLD", "ROU"]
RELEVANT_TERMS = [
    "software",
    "engineer",
    "machine learning",
    "applied scientist",
    "scientist",
    "data scientist",
    "data engineer",
    "backend",
    "frontend",
    "full stack",
    "platform",
    "developer experience",
    "security engineer",
    "devops",
    "site reliability",
]


class UberJobsAdapter(SourceAdapter):
    def __init__(self, source_config: dict):
        super().__init__(source_config)
        self.scraper = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "linux", "mobile": False}
        )
        self.headers = {"content-type": "application/json", "x-csrf-token": "x"}
        self.target_country_codes = list(
            self.source_config.get("target_country_codes") or DEFAULT_TARGET_COUNTRY_CODES
        )

    def discover_openings(self) -> list[SourceListing]:
        listings: list[SourceListing] = []
        seen_ids: set[str] = set()
        limit = int(self.source_config.get("page_size", 10))
        max_pages = int(self.source_config.get("max_pages", 5))
        queries = self.source_config.get("queries") or DEFAULT_QUERIES
        locations = [{"country": code} for code in self.target_country_codes]

        for query in queries:
            for page in range(max_pages):
                payload = {"limit": limit, "page": page, "params": {"location": locations}}
                if query:
                    payload["params"]["query"] = query
                data = self._rpc("loadSearchJobsResults", payload)
                results = data.get("results", [])
                if not results:
                    break
                for item in results:
                    external_id = str(item.get("id") or "")
                    if not external_id or external_id in seen_ids:
                        continue
                    if not _looks_relevant(item):
                        continue
                    target_locations = _target_locations(item, self.target_country_codes)
                    if not target_locations:
                        continue
                    seen_ids.add(external_id)
                    listings.append(
                        SourceListing(
                            external_id=external_id,
                            title=item.get("title", ""),
                            url=_detail_url(external_id),
                            location_text=" | ".join(target_locations),
                            posted_at=_parse_datetime(item.get("creationDate")),
                            metadata=item,
                        )
                    )
                total = _total_results(data.get("totalResults"))
                if (page + 1) * limit >= total:
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
        description_text = _clean_markdown(item.get("description", ""))
        location_text = " | ".join(_target_locations(item, self.target_country_codes))
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
            employment_type=item.get("timeType") or None,
            remote_mode=infer_remote_mode(" ".join([title, location_text, description_text])),
            posted_at=_parse_datetime(item.get("creationDate")),
            description_text=description_text or title,
            requirements_text=item.get("team", "") or item.get("department", ""),
            seniority=_infer_seniority(title),
            employer_class=EmployerClass(self.source_config["employer_class"]),
            language_signals=["en"],
        )

    def _rpc(self, method: str, payload: dict) -> dict:
        response = self.scraper.post(
            f"https://www.uber.com/api/{method}",
            data=json.dumps(payload),
            headers=self.headers,
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("data", {})


def _detail_url(job_id: str) -> str:
    return f"https://www.uber.com/global/en/careers/list/{job_id}/"


def _target_locations(item: dict, target_country_codes: list[str] | None = None) -> list[str]:
    allowed_codes = set(target_country_codes or DEFAULT_TARGET_COUNTRY_CODES)
    locations = item.get("allLocations") or []
    if not locations and isinstance(item.get("location"), dict):
        locations = [item["location"]]
    values: list[str] = []
    for location in locations:
        if not isinstance(location, dict):
            continue
        country_name = location.get("countryName")
        country_code = location.get("country")
        if country_code not in allowed_codes and country_name not in {
            "Germany",
            "Netherlands",
            "Romania",
            "Switzerland",
        }:
            continue
        text = _location_text(location)
        if text and text not in values:
            values.append(text)
    return values


def _location_text(location: dict) -> str:
    parts = [location.get("city"), location.get("region"), location.get("countryName")]
    values: list[str] = []
    for part in parts:
        if part and part not in values:
            values.append(str(part))
    return ", ".join(values)


def _total_results(value: object) -> int:
    if isinstance(value, dict):
        low = value.get("low")
        if isinstance(low, int):
            return low
    if isinstance(value, int):
        return value
    return 0


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _clean_markdown(value: str) -> str:
    if not value:
        return ""
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value)
    text = re.sub(r"[*_`#>]+", " ", text)
    return " ".join(unescape(text).replace("\xa0", " ").split())


def _looks_relevant(item: dict) -> bool:
    haystack = " ".join(
        str(part or "")
        for part in [item.get("title"), item.get("department"), item.get("team")]
    ).lower()
    return any(term in haystack for term in RELEVANT_TERMS)


def _infer_seniority(title: str) -> str | None:
    lowered = title.lower()
    for candidate in ["principal", "staff", "senior", "lead", "manager", "director", "junior"]:
        if candidate in lowered:
            return candidate
    return None
