from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from job_search.enums import ApplicationStatus, Country, EmployerClass


class SourceListing(BaseModel):
    external_id: str
    title: str
    url: str
    location_text: str
    posted_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RawJobPayload(BaseModel):
    source_name: str
    source_job_id: str
    canonical_url: str
    payload: dict[str, Any]


class NormalizedJob(BaseModel):
    source_name: str
    source_job_id: str
    canonical_url: str
    company: str
    title: str
    location_text: str
    country: Country
    location_country_code: str | None = None
    employment_type: str | None = None
    remote_mode: str | None = None
    posted_at: datetime | None = None
    description_text: str
    requirements_text: str = ""
    seniority: str | None = None
    employer_class: EmployerClass = EmployerClass.OTHER
    source_kind: str = "unknown"
    source_priority: int = 0
    role_tags: list[str] = Field(default_factory=list)
    language_signals: list[str] = Field(default_factory=list)
    score: float = 0.0
    score_reasons: list[str] = Field(default_factory=list)
    is_active: bool = True


class ApplicationUpdate(BaseModel):
    status: ApplicationStatus
    notes: str | None = None
    follow_up_date: date | None = None


class RunRequest(BaseModel):
    source_names: list[str] = Field(default_factory=list)


class ApplicationRecord(BaseModel):
    job_id: int
    status: ApplicationStatus
    notes: str
    follow_up_date: date | None = None
    updated_at: datetime


class JobRecord(BaseModel):
    id: int
    source_name: str
    source_job_id: str
    canonical_url: str
    company: str
    title: str
    location_text: str
    country: Country
    location_country_code: str | None = None
    employment_type: str | None = None
    remote_mode: str | None = None
    posted_at: datetime | None = None
    description_text: str
    requirements_text: str = ""
    seniority: str | None = None
    employer_class: EmployerClass
    source_kind: str = "unknown"
    source_priority: int = 0
    role_tags: list[str]
    language_signals: list[str]
    score: float
    score_reasons: list[str]
    is_active: bool
    application_status: ApplicationStatus
    application_notes: str = ""
    follow_up_date: date | None = None
    last_seen_at: datetime
    created_at: datetime
    updated_at: datetime


class SourceRunRecord(BaseModel):
    id: int
    source_name: str
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    discovered_count: int = 0
    inserted_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    error_text: str | None = None


class ListResponse(BaseModel):
    items: list[Any]


class SavedSearchCreate(BaseModel):
    name: str
    filters: dict[str, Any] = Field(default_factory=dict)


class SourceConfigCreate(BaseModel):
    name: str
    company_name: str
    adapter: str
    country: Country
    employer_class: EmployerClass
    source_kind: str | None = None
    priority_weight: int = 3
    careers_url: str
    board_token: str | None = None
    company_slug: str | None = None
    company_identifier: str | None = None
    max_pages: int | None = None
    limit: int | None = None
    jobs: list[dict[str, Any]] = Field(default_factory=list)


class SearchProfile(BaseModel):
    target_countries: list[str] = Field(default_factory=list)
    priority_keywords: list[str] = Field(default_factory=list)
    excluded_keywords: list[str] = Field(default_factory=list)
    required_role_tags_any: list[str] = Field(default_factory=list)
