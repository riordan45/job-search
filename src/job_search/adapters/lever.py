from __future__ import annotations

from datetime import datetime

from job_search.adapters.base import SourceAdapter
from job_search.adapters.http import fetch_json
from job_search.enums import Country, EmployerClass
from job_search.models import NormalizedJob, RawJobPayload, SourceListing
from job_search.scoring import detect_country, infer_remote_mode


class LeverAdapter(SourceAdapter):
    def discover_openings(self) -> list[SourceListing]:
        company = self.source_config["company_slug"]
        data = fetch_json(f"https://api.lever.co/v0/postings/{company}?mode=json")
        return [
            SourceListing(
                external_id=item["id"],
                title=item["text"],
                url=item["hostedUrl"],
                location_text=item.get("categories", {}).get("location", ""),
                metadata=item,
            )
            for item in data
        ]

    def fetch_job(self, listing: SourceListing) -> RawJobPayload:
        return RawJobPayload(
            source_name=self.source_config["name"],
            source_job_id=listing.external_id,
            canonical_url=listing.url,
            payload=listing.metadata,
        )

    def normalize(self, payload: RawJobPayload) -> NormalizedJob:
        data = payload.payload
        metadata = self.source_config
        description = "\n".join(
            [
                data.get("descriptionPlain", ""),
                data.get("lists", [{}])[0].get("text", "") if data.get("lists") else "",
            ]
        )
        return NormalizedJob(
            source_name=payload.source_name,
            source_job_id=payload.source_job_id,
            canonical_url=payload.canonical_url,
            company=metadata["company_name"],
            title=data["text"],
            location_text=data.get("categories", {}).get("location", ""),
            country=Country(
                detect_country(
                    f'{data.get("categories", {}).get("location", "")} {description}',
                    default=metadata.get("country"),
                )
                or metadata["country"]
            ),
            remote_mode=infer_remote_mode(data["text"] + " " + description),
            posted_at=_parse_epoch(data.get("createdAt")),
            description_text=description,
            requirements_text=description,
            seniority=_infer_seniority(data["text"]),
            employer_class=EmployerClass(metadata["employer_class"]),
            language_signals=["en"],
        )


def _parse_epoch(value: int | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value / 1000)


def _infer_seniority(title: str) -> str | None:
    lowered = title.lower()
    for candidate in ["staff", "senior", "lead", "principal", "mid"]:
        if candidate in lowered:
            return candidate
    return None
