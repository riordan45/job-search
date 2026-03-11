from __future__ import annotations

import json
import re

import cloudscraper

from job_search.adapters.base import SourceAdapter
from job_search.enums import Country, EmployerClass
from job_search.models import NormalizedJob, RawJobPayload, SourceListing
from job_search.scoring import detect_country, infer_remote_mode


NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)
TARGET_COUNTRY_NAMES = {"Switzerland", "Germany", "Netherlands", "Romania"}


class RevolutJobsAdapter(SourceAdapter):
    def __init__(self, source_config: dict):
        super().__init__(source_config)
        self.scraper = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "linux", "mobile": False}
        )
        configured = self.source_config.get("target_country_names") or sorted(TARGET_COUNTRY_NAMES)
        self.target_country_names = set(configured)

    def discover_openings(self) -> list[SourceListing]:
        html = self._fetch_text(self.source_config["careers_url"])
        positions = _extract_positions(html)
        listings: list[SourceListing] = []
        for item in positions:
            target_locations = _target_locations(item, self.target_country_names)
            if not target_locations:
                continue
            external_id = str(item["id"])
            listings.append(
                SourceListing(
                    external_id=external_id,
                    title=item.get("text", ""),
                    url=_position_url(external_id),
                    location_text=" | ".join(target_locations),
                    metadata=item,
                )
            )
        return listings

    def fetch_job(self, listing: SourceListing) -> RawJobPayload:
        html = self._fetch_text(listing.url)
        return RawJobPayload(
            source_name=self.source_config["name"],
            source_job_id=listing.external_id,
            canonical_url=listing.url,
            payload={
                "position": _extract_position(html) or listing.metadata,
                "listing": listing.metadata,
            },
        )

    def normalize(self, payload: RawJobPayload) -> NormalizedJob:
        position = payload.payload.get("position") or payload.payload.get("listing", {})
        title = position.get("text", "")
        description_text = _clean_html(position.get("description", ""))
        target_locations = _target_locations(position, self.target_country_names)
        location_text = " | ".join(target_locations)
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
            remote_mode=infer_remote_mode(" ".join([title, location_text, description_text])),
            posted_at=None,
            description_text=description_text or title,
            requirements_text=position.get("team", ""),
            seniority=_infer_seniority(title),
            employer_class=EmployerClass(self.source_config["employer_class"]),
            language_signals=["en"],
        )

    def _fetch_text(self, url: str) -> str:
        response = self.scraper.get(url, timeout=30)
        response.raise_for_status()
        return response.text


def _extract_positions(html: str) -> list[dict]:
    page_props = _page_props(html)
    positions = page_props.get("positions")
    if not isinstance(positions, list):
        return []
    return [item for item in positions if isinstance(item, dict) and item.get("id")]


def _extract_position(html: str) -> dict:
    page_props = _page_props(html)
    position = page_props.get("position")
    if isinstance(position, dict):
        return position
    return {}


def _page_props(html: str) -> dict:
    match = NEXT_DATA_RE.search(html)
    if not match:
        return {}
    payload = json.loads(match.group(1))
    return payload.get("props", {}).get("pageProps", {})


def _target_locations(item: dict, target_country_names: set[str] | None = None) -> list[str]:
    allowed = target_country_names or TARGET_COUNTRY_NAMES
    values: list[str] = []
    for location in item.get("locations") or []:
        if not isinstance(location, dict):
            continue
        country_name = location.get("country")
        name = location.get("name")
        if country_name not in allowed or not name:
            continue
        text = str(name)
        if text not in values:
            values.append(text)
    return values


def _position_url(position_id: str) -> str:
    return f"https://www.revolut.com/en-RO/careers/position/{position_id}/"


def _clean_html(value: str) -> str:
    if not value:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    text = re.sub(r"</p\s*>", "\n\n", text, flags=re.I)
    text = re.sub(r"<li[^>]*>", "- ", text, flags=re.I)
    text = re.sub(r"</li>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(text.replace("\xa0", " ").split())


def _infer_seniority(title: str) -> str | None:
    lowered = title.lower()
    for candidate in ["principal", "staff", "senior", "lead", "manager", "director", "mid/senior", "junior"]:
        if candidate in lowered:
            return candidate
    return None
