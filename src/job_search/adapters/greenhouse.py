from __future__ import annotations

from datetime import datetime

from job_search.adapters.base import SourceAdapter
from job_search.adapters.http import fetch_json
from job_search.enums import Country, EmployerClass
from job_search.models import NormalizedJob, RawJobPayload, SourceListing
from job_search.scoring import detect_country, infer_remote_mode


class GreenhouseAdapter(SourceAdapter):
    def discover_openings(self) -> list[SourceListing]:
        board = self.source_config["board_token"]
        data = fetch_json(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs")
        listings = []
        for item in data.get("jobs", []):
            listings.append(
                SourceListing(
                    external_id=str(item["id"]),
                    title=item["title"],
                    url=item["absolute_url"],
                    location_text=item.get("location", {}).get("name", ""),
                    metadata=item,
                )
            )
        return listings

    def fetch_job(self, listing: SourceListing) -> RawJobPayload:
        board = self.source_config["board_token"]
        detail = fetch_json(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{listing.external_id}")
        return RawJobPayload(
            source_name=self.source_config["name"],
            source_job_id=listing.external_id,
            canonical_url=detail.get("absolute_url", listing.url),
            payload=detail,
        )

    def normalize(self, payload: RawJobPayload) -> NormalizedJob:
        data = payload.payload
        description_parts = [data.get("content", "")]
        metadata = self.source_config
        location_text = _greenhouse_location_text(data)
        detected_country = detect_country(
            " ".join(
                [
                    location_text,
                    data.get("title", ""),
                    data.get("content", ""),
                    _metadata_text(data.get("metadata")),
                ]
            ),
            default=metadata.get("country"),
        )
        return NormalizedJob(
            source_name=payload.source_name,
            source_job_id=payload.source_job_id,
            canonical_url=payload.canonical_url,
            company=metadata["company_name"],
            title=data["title"],
            location_text=location_text,
            country=Country(detected_country or metadata["country"]),
            location_country_code=_greenhouse_country_code(data),
            employment_type=None,
            remote_mode=infer_remote_mode(data.get("title", "") + " " + data.get("content", "")),
            posted_at=_parse_datetime(data.get("updated_at")),
            description_text="\n".join(part for part in description_parts if part),
            seniority=_infer_seniority(data["title"]),
            employer_class=EmployerClass(metadata["employer_class"]),
            language_signals=["en"],
        )


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _infer_seniority(title: str) -> str | None:
    lowered = title.lower()
    for candidate in ["staff", "senior", "lead", "principal", "mid"]:
        if candidate in lowered:
            return candidate
    return None


def _metadata_text(metadata: list[dict] | None) -> str:
    if not metadata:
        return ""
    values: list[str] = []
    for item in metadata:
        name = str(item.get("name", "")).lower()
        if "location" not in name and "country" not in name and "region" not in name:
            continue
        value = item.get("value")
        if isinstance(value, list):
            values.extend(str(entry) for entry in value)
        elif value is not None:
            values.append(str(value))
    return " ".join(values)


def _greenhouse_location_text(data: dict) -> str:
    base = data.get("location", {}).get("name", "")
    office_names = ", ".join(
        office.get("name", "") for office in data.get("offices", []) if office.get("name")
    )
    if office_names and office_names not in base:
        return " · ".join(part for part in [base, office_names] if part).strip()
    return base


def _greenhouse_country_code(data: dict) -> str | None:
    for office in data.get("offices", []):
        name = str(office.get("name", ""))
        prefix = name.split("-", 1)[0].strip().upper()
        if len(prefix) == 2 and prefix.isalpha():
            return prefix
    return None
