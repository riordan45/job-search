from __future__ import annotations

from threading import Event, Lock, Thread
from time import sleep

from job_search.config import (
    load_active_company_targets,
    load_company_targets,
    load_profile,
    save_local_company_target,
    save_profile,
)
from job_search.ingest import IngestionService
from job_search.models import (
    ApplicationUpdate,
    SavedSearchCreate,
    SearchProfile,
    SourceConfigCreate,
)
from job_search.repository import Repository
from job_search.scoring import matches_search_profile


class JobSearchService:
    def __init__(self, repository: Repository | None = None):
        self.repository = repository or Repository()
        self.repository.mark_running_runs_abandoned()
        self.ingestion = IngestionService(self.repository)
        self._scheduler_stop = Event()
        self._scheduler_thread: Thread | None = None
        self._run_lock = Lock()
        self._run_thread: Thread | None = None
        self._revalidate_jobs()

    def run_once(self, source_names: list[str] | None = None) -> list[dict]:
        with self._run_lock:
            summaries = [summary.__dict__ for summary in self.ingestion.run(source_names)]
            self._revalidate_jobs()
            return summaries

    def start_run_background(self, source_names: list[str] | None = None) -> bool:
        if self.is_run_in_progress():
            return False

        def _runner() -> None:
            try:
                self.run_once(source_names)
            finally:
                self._run_thread = None

        self._run_thread = Thread(target=_runner, daemon=True)
        self._run_thread.start()
        return True

    def is_run_in_progress(self) -> bool:
        return self._run_thread is not None and self._run_thread.is_alive()

    def list_jobs(self, **filters):
        return self.repository.list_jobs(**filters)

    def get_job(self, job_id: int):
        return self.repository.get_job(job_id)

    def update_application(self, job_id: int, update: ApplicationUpdate):
        return self.repository.update_application(
            job_id,
            status=update.status,
            notes=update.notes,
            follow_up_date=update.follow_up_date,
        )

    def list_runs(self):
        return self.repository.list_runs()

    def run_status(self) -> dict[str, bool]:
        return {"running": self.is_run_in_progress()}

    def list_filters(self):
        return {
            "countries": ["CH", "DE", "NL", "RO"],
            "employer_classes": [
                "big_tech",
                "finance",
                "startup",
                "enterprise",
                "research_public",
                "other",
            ],
            "application_statuses": [
                "new",
                "saved",
                "reviewing",
                "applied",
                "rejected",
                "closed",
                "ignore",
            ],
            "saved_searches": self.repository.list_saved_searches(),
        }

    def list_sources(self) -> list[dict]:
        return load_active_company_targets()

    def create_source(self, source: SourceConfigCreate) -> dict:
        return save_local_company_target(source.model_dump(mode="json"))

    def save_search(self, search: SavedSearchCreate) -> dict:
        return self.repository.save_search(search.name, search.filters)

    def get_search_profile(self) -> dict:
        return load_profile()

    def update_search_profile(self, profile: SearchProfile) -> dict:
        saved = save_profile(profile.model_dump(mode="json"))
        self._revalidate_jobs()
        return saved

    def _revalidate_jobs(self) -> None:
        profile = load_profile()
        for job in self.repository.list_jobs(include_inactive=True):
            self.repository.set_job_active(job.id, is_active=matches_search_profile(job, profile))

    def ensure_scheduler(self, interval_seconds: int = 86400) -> None:
        if self._scheduler_thread and self._scheduler_thread.is_alive():
            return

        def _loop() -> None:
            while not self._scheduler_stop.is_set():
                sleep(interval_seconds)
                if not self._scheduler_stop.is_set() and not self.is_run_in_progress():
                    self.start_run_background()

        self._scheduler_thread = Thread(target=_loop, daemon=True)
        self._scheduler_thread.start()

    def stop_scheduler(self) -> None:
        self._scheduler_stop.set()
