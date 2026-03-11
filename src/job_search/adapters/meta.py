from __future__ import annotations

from datetime import datetime
from html import unescape
import json
import re
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener
import http.cookiejar

from job_search.adapters.base import SourceAdapter
from job_search.adapters.http import fetch_text
from job_search.enums import Country, EmployerClass
from job_search.models import NormalizedJob, RawJobPayload, SourceListing
from job_search.scoring import detect_country, infer_remote_mode


SEARCH_PAGE_URL = "https://www.metacareers.com/jobsearch/"
GRAPHQL_URL = "https://www.metacareers.com/api/graphql/"
DETAIL_URL_TEMPLATE = "https://www.metacareers.com/jobs/{job_id}/"
SEARCH_DOC_ID = "26228555073499023"
LOCATION_DOC_ID = "24867916029505828"
RESULTS_PER_PAGE = "FIFTY"
DEFAULT_TARGET_COUNTRIES = ["Germany", "Netherlands", "Romania", "Switzerland"]
LSD_RE = re.compile(r'LSD",\[\],\{"token":"([^"]+)"')
JSON_LD_RE = re.compile(r'<script type="application/ld\+json"[^>]*>\s*(\{.*?\})\s*</script>', re.S)


class MetaCareersAdapter(SourceAdapter):
    def discover_openings(self) -> list[SourceListing]:
        session = _MetaCareersSession()
        target_countries = self.source_config.get("target_country_names", DEFAULT_TARGET_COUNTRIES)
        office_queries = _target_office_queries(session.fetch_location_filters(), target_countries)

        listings: list[SourceListing] = []
        seen_ids: set[str] = set()
        for office_query in office_queries:
            for item in session.search_jobs(office_query):
                target_locations = _target_locations(item.get("locations", []), target_countries)
                if not target_locations:
                    continue
                external_id = str(item["id"])
                if external_id in seen_ids:
                    continue
                seen_ids.add(external_id)
                listings.append(
                    SourceListing(
                        external_id=external_id,
                        title=item["title"],
                        url=_detail_url(external_id),
                        location_text=" | ".join(target_locations),
                        metadata={
                            "title": item["title"],
                            "locations": target_locations,
                            "office_query": office_query,
                        },
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
        posting = _extract_job_posting(payload.payload["html"])
        listing = payload.payload["listing"]
        target_countries = self.source_config.get("target_country_names", DEFAULT_TARGET_COUNTRIES)
        location_text = _location_text(posting, listing.get("location_text", ""), target_countries)
        country = detect_country(location_text, default=self.source_config.get("country"))
        description_parts = [
            _clean_text(posting.get("description", "")),
            _clean_text(posting.get("responsibilities", "")),
        ]
        requirements = _clean_text(posting.get("qualifications", ""))

        return NormalizedJob(
            source_name=payload.source_name,
            source_job_id=payload.source_job_id,
            canonical_url=payload.canonical_url,
            company=self.source_config["company_name"],
            title=posting.get("title", listing.get("title", "")),
            location_text=location_text,
            country=Country(country or self.source_config["country"]),
            location_country_code=country,
            employment_type=posting.get("employmentType"),
            remote_mode=infer_remote_mode(
                " ".join(
                    [
                        posting.get("title", ""),
                        location_text,
                        posting.get("description", ""),
                        posting.get("responsibilities", ""),
                    ]
                )
            ),
            posted_at=_parse_datetime(posting.get("datePosted")),
            description_text="\n\n".join(part for part in description_parts if part),
            requirements_text=requirements,
            seniority=_infer_seniority(posting.get("title", listing.get("title", ""))),
            employer_class=EmployerClass(self.source_config["employer_class"]),
            language_signals=["en"],
        )


class _MetaCareersSession:
    def __init__(self) -> None:
        cookie_jar = http.cookiejar.CookieJar()
        self.opener = build_opener(HTTPCookieProcessor(cookie_jar))
        self.lsd_token = self._bootstrap()

    def fetch_location_filters(self) -> dict:
        return self._graphql_query(
            doc_id=LOCATION_DOC_ID,
            friendly_name="CareersJobSearchLocationFilterV3Query",
            variables={"search_input": {"q": "", "results_per_page": RESULTS_PER_PAGE}},
        )

    def search_jobs(self, office_query: str) -> list[dict]:
        payload = self._graphql_query(
            doc_id=SEARCH_DOC_ID,
            friendly_name="CareersJobSearchInputDropdownDataQuery",
            variables={"search_input": {"q": office_query, "results_per_page": RESULTS_PER_PAGE}},
        )
        return payload.get("data", {}).get("job_search_with_featured_jobs", {}).get("all_jobs", [])

    def _bootstrap(self) -> str:
        request = Request(
            SEARCH_PAGE_URL,
            headers={"User-Agent": "job-search/0.1 (+local-first tracker)", "Accept": "text/html"},
        )
        with self.opener.open(request, timeout=20) as response:
            html = response.read().decode("utf-8", errors="ignore")
        token = _extract_lsd_token(html)
        if not token:
            raise ValueError("Meta Careers LSD token not found")
        return token

    def _graphql_query(self, *, doc_id: str, friendly_name: str, variables: dict) -> dict:
        body = urlencode(
            {
                "lsd": self.lsd_token,
                "__user": "0",
                "__a": "1",
                "fb_api_req_friendly_name": friendly_name,
                "variables": json.dumps(variables, separators=(",", ":")),
                "doc_id": doc_id,
            }
        ).encode("utf-8")
        request = Request(
            GRAPHQL_URL,
            data=body,
            method="POST",
            headers={
                "User-Agent": "job-search/0.1 (+local-first tracker)",
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
        )
        try:
            with self.opener.open(request, timeout=20) as response:
                raw = response.read().decode("utf-8", errors="ignore")
        except HTTPError as exc:
            raise ValueError(f"Meta Careers GraphQL request failed: {exc.code}") from exc
        return json.loads(raw.removeprefix("for (;;);"))


def _extract_lsd_token(html: str) -> str | None:
    match = LSD_RE.search(html)
    return match.group(1) if match else None


def _target_office_queries(payload: dict, target_countries: list[str]) -> list[str]:
    seen: set[str] = set()
    office_queries: list[str] = []
    locations = payload.get("data", {}).get("job_search_filters", {}).get("locations", [])
    for location in locations:
        if location.get("is_remote"):
            continue
        if location.get("country") not in target_countries:
            continue
        display_name = str(location.get("location_display_name", "")).strip()
        if not display_name or "," not in display_name:
            continue
        office_query = display_name.split(",", 1)[0].strip()
        if office_query in seen:
            continue
        seen.add(office_query)
        office_queries.append(office_query)
    return office_queries


def _target_locations(locations: list[str], target_countries: list[str]) -> list[str]:
    target_locations: list[str] = []
    for location in locations:
        if any(location.endswith(country) for country in target_countries):
            target_locations.append(location)
    return target_locations


def _detail_url(job_id: str) -> str:
    return DETAIL_URL_TEMPLATE.format(job_id=job_id)


def _extract_job_posting(html: str) -> dict:
    for match in JSON_LD_RE.finditer(html):
        payload = json.loads(unescape(match.group(1)))
        if payload.get("@type") == "JobPosting":
            return payload
    raise ValueError("Meta Careers job posting JSON-LD not found")


def _location_text(posting: dict, fallback: str, target_countries: list[str]) -> str:
    locations = posting.get("jobLocation", [])
    names = [str(location.get("name", "")).strip() for location in locations if location.get("name")]
    target_names = _target_locations(names, target_countries)
    if target_names:
        return " | ".join(target_names)
    if names:
        return " | ".join(names)
    return fallback


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def _clean_text(value: str) -> str:
    return " ".join(unescape(str(value)).replace("\xa0", " ").split())


def _infer_seniority(title: str) -> str | None:
    lowered = title.lower()
    for candidate in ["staff", "senior", "lead", "principal", "manager", "intern"]:
        if candidate in lowered:
            return candidate
    return None
