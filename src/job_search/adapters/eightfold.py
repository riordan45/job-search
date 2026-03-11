from __future__ import annotations

from datetime import datetime, timezone
from html import unescape
import re
from urllib.parse import urlencode, urlsplit

from job_search.adapters.base import SourceAdapter
from job_search.adapters.http import fetch_json
from job_search.enums import Country, EmployerClass
from job_search.models import NormalizedJob, RawJobPayload, SourceListing
from job_search.scoring import COUNTRY_ALIASES, detect_country, infer_remote_mode


class EightfoldAdapter(SourceAdapter):
    def discover_openings(self) -> list[SourceListing]:
        listings: list[SourceListing] = []
        seen_ids: set[str] = set()
        careers_url = self.source_config["careers_url"]
        search_locations = self.source_config.get("search_locations", [])
        page_size = int(self.source_config.get("page_size", 10))
        max_pages = int(self.source_config.get("max_pages", 5))
        for location in search_locations:
            for page in range(max_pages):
                start = page * page_size
                data = fetch_json(_search_url(careers_url, self.source_config["domain"], location, start=start))
                result = data.get("data", {})
                positions = result.get("positions", [])
                if not positions:
                    break
                for item in positions:
                    job_id = str(item["id"])
                    if job_id in seen_ids:
                        continue
                    target_locations = _target_locations(item)
                    if not target_locations:
                        continue
                    seen_ids.add(job_id)
                    listings.append(
                        SourceListing(
                            external_id=job_id,
                            title=item.get("name", ""),
                            url=_detail_page_url(careers_url, item["id"]),
                            location_text=" | ".join(target_locations),
                            posted_at=_from_ts(item.get("postedTs")),
                            metadata={"listing": item, "queried_location": location},
                        )
                    )
                if len(positions) < page_size:
                    break
        return listings

    def fetch_job(self, listing: SourceListing) -> RawJobPayload:
        detail = fetch_json(
            _detail_api_url(
                self.source_config["careers_url"],
                self.source_config["domain"],
                listing.external_id,
            )
        )
        return RawJobPayload(
            source_name=self.source_config["name"],
            source_job_id=listing.external_id,
            canonical_url=listing.url,
            payload={
                "detail": detail.get("data", {}),
                "listing": listing.metadata.get("listing", {}),
                "queried_location": listing.metadata.get("queried_location"),
            },
        )

    def normalize(self, payload: RawJobPayload) -> NormalizedJob:
        detail = payload.payload.get("detail", {})
        listing = payload.payload.get("listing", {})
        title = detail.get("name") or listing.get("name", "")
        target_locations = _target_locations(detail or listing)
        location_text = " | ".join(target_locations)
        country_code = detect_country(location_text, default=self.source_config.get("country"))
        job_description = _clean_html(detail.get("jobDescription", ""))
        qualifications = _clean_html(detail.get("qualifications", ""))

        return NormalizedJob(
            source_name=payload.source_name,
            source_job_id=payload.source_job_id,
            canonical_url=payload.canonical_url,
            company=self.source_config["company_name"],
            title=title,
            location_text=location_text,
            country=Country(country_code or self.source_config["country"]),
            location_country_code=country_code,
            remote_mode=infer_remote_mode(" ".join([title, location_text, job_description])),
            posted_at=_from_ts(detail.get("postedTs") or listing.get("postedTs")),
            description_text=job_description,
            requirements_text=qualifications,
            seniority=_infer_seniority(title),
            employer_class=EmployerClass(self.source_config["employer_class"]),
            language_signals=["en"],
        )


def _search_url(careers_url: str, domain: str, location: str, *, start: int) -> str:
    params = {
        "domain": domain,
        "location": location,
        "start": str(start),
        "sort_by": "distance",
        "filter_include_remote": "1",
    }
    return f"{_origin(careers_url)}/api/pcsx/search?{urlencode(params)}"


def _detail_api_url(careers_url: str, domain: str, position_id: str) -> str:
    params = {"domain": domain, "position_id": position_id}
    return f"{_origin(careers_url)}/api/pcsx/position_details?{urlencode(params)}"


def _detail_page_url(careers_url: str, position_id: str | int) -> str:
    return f"{_origin(careers_url)}/careers/job/{position_id}"


def _origin(careers_url: str) -> str:
    parsed = urlsplit(careers_url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _target_locations(item: dict) -> list[str]:
    raw_locations = item.get("locations") or []
    standardized = item.get("standardizedLocations") or []
    merged = [*raw_locations, *standardized]
    kept: list[str] = []
    for value in merged:
        text = str(value).strip()
        country = detect_country(text)
        if country in COUNTRY_ALIASES and text not in kept:
            kept.append(text)
    return kept


def _from_ts(value: int | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromtimestamp(int(value), tz=timezone.utc)


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
    for candidate in ["principal", "staff", "senior", "lead", "manager", "director"]:
        if candidate in lowered:
            return candidate
    return None
