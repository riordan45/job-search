from __future__ import annotations

from abc import ABC, abstractmethod

from job_search.models import NormalizedJob, RawJobPayload, SourceListing


class SourceAdapter(ABC):
    def __init__(self, source_config: dict):
        self.source_config = source_config

    @abstractmethod
    def discover_openings(self) -> list[SourceListing]:
        raise NotImplementedError

    @abstractmethod
    def fetch_job(self, listing: SourceListing) -> RawJobPayload:
        raise NotImplementedError

    @abstractmethod
    def normalize(self, payload: RawJobPayload) -> NormalizedJob:
        raise NotImplementedError
