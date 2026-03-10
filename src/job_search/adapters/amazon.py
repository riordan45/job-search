from __future__ import annotations

from datetime import datetime
from html import unescape
import json
import re
from urllib.parse import urlencode

from job_search.adapters.base import SourceAdapter
from job_search.adapters.http import fetch_json
from job_search.enums import Country, EmployerClass
from job_search.models import NormalizedJob, RawJobPayload, SourceListing
from job_search.scoring import detect_country


TARGET_COUNTRY_CODES = ("DEU", "CHE", "NLD", "ROU")
ISO3_TO_COUNTRY = {
    "DEU": Country.DE,
    "CHE": Country.CH,
    "NLD": Country.NL,
    "ROU": Country.RO,
}


class AmazonJobsAdapter(SourceAdapter):
    def discover_openings(self) -> list[SourceListing]:
        listings: list[SourceListing] = []
        seen_ids: set[str] = set()
        page_size = int(self.source_config.get("page_size", 10))
        max_pages = int(self.source_config.get("max_pages", 10))
        queries = self.source_config.get("queries") or [self.source_config.get("query", "software engineer")]
        country_codes = self.source_config.get("target_country_codes", list(TARGET_COUNTRY_CODES))

        for query in queries:
            for page in range(max_pages):
                offset = page * page_size
                data = fetch_json(_search_url(query=query, offset=offset, page_size=page_size, country_codes=country_codes))
                jobs = data.get("jobs", [])
                if not jobs:
                    break
                for item in jobs:
                    country_code = str(item.get("country_code", "")).upper()
                    location_text = _location_text(item)
                    if country_code and country_code not in country_codes:
                        continue
                    if not country_code and not detect_country(location_text):
                        continue
                    job_id = str(item.get("id_icims") or "")
                    if not job_id or job_id in seen_ids:
                        continue
                    seen_ids.add(job_id)
                    listings.append(
                        SourceListing(
                            external_id=job_id,
                            title=item.get("title", ""),
                            url=_detail_url(item),
                            location_text=location_text,
                            posted_at=_parse_posted_date(item.get("posted_date")),
                            metadata=item,
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
        location_text = _location_text(item)
        country = _country_from_item(item, location_text, default=self.source_config.get("country"))

        return NormalizedJob(
            source_name=payload.source_name,
            source_job_id=payload.source_job_id,
            canonical_url=payload.canonical_url,
            company=self.source_config["company_name"],
            title=item.get("title", ""),
            location_text=location_text,
            country=country,
            location_country_code=country.value,
            posted_at=_parse_posted_date(item.get("posted_date")),
            description_text=_clean_html(item.get("description", "")),
            requirements_text="\n\n".join(
                part
                for part in [
                    _clean_html(item.get("basic_qualifications", "")),
                    _clean_html(item.get("preferred_qualifications", "")),
                ]
                if part
            ),
            seniority=_infer_seniority(item.get("title", "")),
            employer_class=EmployerClass(self.source_config["employer_class"]),
            language_signals=["en"],
        )


def _search_url(*, query: str, offset: int, page_size: int, country_codes: list[str]) -> str:
    params: list[tuple[str, str | int]] = [("offset", offset), ("size", page_size)]
    if query:
        params.append(("base_query", query))
    for code in country_codes:
        params.append(("normalized_country_code[]", code))
    return f"https://www.amazon.jobs/en/search.json?{urlencode(params)}"


def _detail_url(item: dict) -> str:
    job_path = str(item.get("job_path", "")).strip()
    if job_path.startswith("http://") or job_path.startswith("https://"):
        return job_path
    return f"https://www.amazon.jobs{job_path}"


def _location_text(item: dict) -> str:
    parsed = _parsed_locations(item)
    if parsed:
        return " | ".join(parsed)
    return str(item.get("location", "")).strip()


def _parsed_locations(item: dict) -> list[str]:
    parsed: list[str] = []
    for raw in item.get("locations", []):
        if isinstance(raw, dict):
            location = raw
        else:
            try:
                location = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                continue
        country = str(location.get("normalizedCountryName") or location.get("countryIso3a") or "").strip()
        state = str(location.get("normalizedStateName") or "").strip()
        city = str(location.get("city") or "").strip()
        parts: list[str] = []
        for part in [city, state, country]:
            if part and part not in parts:
                parts.append(part)
        value = ", ".join(parts)
        if value and value not in parsed:
            parsed.append(value)
    return parsed


def _country_from_item(item: dict, location_text: str, default: str | None) -> Country:
    country_code = str(item.get("country_code", "")).upper()
    if country_code in ISO3_TO_COUNTRY:
        return ISO3_TO_COUNTRY[country_code]
    detected = detect_country(location_text, default=default)
    return Country(detected or default or Country.DE.value)


def _parse_posted_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%B %d, %Y")
    except ValueError:
        return None


def _clean_html(value: str) -> str:
    if not value:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    text = re.sub(r"</p\s*>", "\n\n", text, flags=re.I)
    text = re.sub(r"<li>", "- ", text, flags=re.I)
    text = re.sub(r"</li>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(unescape(text).replace("\xa0", " ").split())


def _infer_seniority(title: str) -> str | None:
    lowered = title.lower()
    for candidate in ["principal", "staff", "senior", "lead", "manager"]:
        if candidate in lowered:
            return candidate
    return None
