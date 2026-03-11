from __future__ import annotations

from datetime import datetime
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
from job_search.scoring import extract_language_signals, matches_search_profile


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

    def run_status(self) -> dict:
        running = self.is_run_in_progress()
        runs = self.repository.list_runs()
        current_started_at = _current_run_started_at(runs) if running else None
        current_runs = [
            run
            for run in runs
            if current_started_at and run.started_at >= current_started_at
        ]
        running_sources = [run.source_name for run in current_runs if run.status == "running"]
        finished_runs = [run for run in current_runs if run.status != "running"]
        failed_runs = [run.source_name for run in current_runs if run.status in {"failed", "abandoned"}]
        return {
            "running": running,
            "running_sources": running_sources,
            "completed_sources": len(finished_runs),
            "total_sources": len(current_runs) if current_runs else 0,
            "failed_sources": failed_runs,
        }

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

    def list_sources(self, *, include_demo: bool = False, include_disabled: bool = False) -> list[dict]:
        targets = load_company_targets() if include_disabled else load_active_company_targets(include_demo=include_demo)
        if include_disabled and not include_demo:
            targets = [target for target in targets if not target.get("is_demo")]

        metrics = self.repository.source_metrics()
        items: list[dict] = []
        for target in targets:
            source_metrics = {
                "run_count": 0,
                "success_rate": 0.0,
                "last_run_status": None,
                "last_run_started_at": None,
                "discovered_total": 0,
                "inserted_total": 0,
                "updated_total": 0,
                "skipped_total": 0,
                "retained_job_count": 0,
                "yield_rate": 0.0,
                **metrics.get(target["name"], {}),
            }
            items.append({**target, **source_metrics, "enabled": target.get("enabled", True)})
        return items

    def create_source(self, source: SourceConfigCreate) -> dict:
        return save_local_company_target(source.model_dump(mode="json"))

    def update_source(self, source_name: str, source: SourceConfigCreate) -> dict:
        payload = source.model_dump(mode="json")
        payload["name"] = source_name
        return save_local_company_target(payload)

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
            self.repository.refresh_job_profile_fields(
                job.id,
                is_active=matches_search_profile(job, profile),
                language_signals=extract_language_signals(
                    job.title,
                    job.description_text,
                    job.requirements_text,
                ),
            )

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


def _current_run_started_at(runs: list) -> datetime | None:
    running_runs = [run for run in runs if run.status == "running"]
    if not running_runs:
        return None
    return min(run.started_at for run in running_runs)
