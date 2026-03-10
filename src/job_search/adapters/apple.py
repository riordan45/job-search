from __future__ import annotations

from datetime import datetime
from html import unescape
import json
import re

from job_search.adapters.base import SourceAdapter
from job_search.adapters.http import fetch_text
from job_search.enums import Country, EmployerClass
from job_search.models import NormalizedJob, RawJobPayload, SourceListing
from job_search.scoring import detect_country


HYDRATION_RE = re.compile(r"window\.__staticRouterHydrationData = JSON\.parse\(\"(.*?)\"\);</script>", re.S)


class AppleJobsAdapter(SourceAdapter):
    def discover_openings(self) -> list[SourceListing]:
        listings: list[SourceListing] = []
        seen_ids: set[str] = set()
        max_pages = int(self.source_config.get("max_pages", 20))
        for page in range(1, max_pages + 1):
            html = fetch_text(_search_url(page))
            search_data = _extract_search_data(html)
            results = search_data.get("searchResults", [])
            if not results:
                break
            for item in results:
                location_text = ", ".join(location["name"] for location in item.get("locations", []))
                if not detect_country(location_text):
                    continue
                job_id = str(item["positionId"])
                if job_id in seen_ids:
                    continue
                seen_ids.add(job_id)
                listings.append(
                    SourceListing(
                        external_id=job_id,
                        title=item["postingTitle"],
                        url=_detail_url(item["positionId"], item.get("transformedPostingTitle", "")),
                        location_text=location_text,
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
        location_text = ", ".join(location["name"] for location in item.get("locations", []))
        country = detect_country(location_text, default=self.source_config.get("country"))
        summary = _clean_text(item.get("jobSummary", ""))
        team = item.get("team", {}).get("teamName", "")

        return NormalizedJob(
            source_name=payload.source_name,
            source_job_id=payload.source_job_id,
            canonical_url=payload.canonical_url,
            company=self.source_config["company_name"],
            title=item.get("postingTitle", ""),
            location_text=location_text,
            country=Country(country or self.source_config["country"]),
            location_country_code=country,
            posted_at=_parse_datetime(item.get("postDateInGMT")),
            description_text=summary,
            requirements_text=team,
            seniority=None,
            employer_class=EmployerClass(self.source_config["employer_class"]),
            language_signals=["en"],
        )


def _search_url(page: int) -> str:
    return f"https://jobs.apple.com/en-us/search?page={page}"


def _detail_url(position_id: str, slug: str) -> str:
    if slug:
        return f"https://jobs.apple.com/en-us/details/{position_id}/{slug}"
    return f"https://jobs.apple.com/en-us/details/{position_id}"


def _extract_search_data(html: str) -> dict:
    match = HYDRATION_RE.search(html)
    if not match:
        return {"searchResults": []}
    raw = match.group(1).encode("utf-8").decode("unicode_escape")
    data = json.loads(raw)
    return data["loaderData"]["search"]


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _clean_text(value: str) -> str:
    return " ".join(unescape(value).replace("\xa0", " ").split())
