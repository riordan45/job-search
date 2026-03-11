from __future__ import annotations

from contextlib import asynccontextmanager
import os

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from job_search.models import (
    ApplicationUpdate,
    ListResponse,
    RunRequest,
    SavedSearchCreate,
    SearchProfile,
    SourceConfigCreate,
)
from job_search.service import JobSearchService


def create_app(service: JobSearchService | None = None) -> FastAPI:
    service = service or JobSearchService()
    enable_scheduler = os.getenv("JOB_SEARCH_ENABLE_SCHEDULER", "").lower() in {"1", "true", "yes"}

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if enable_scheduler:
            service.ensure_scheduler()
        try:
            yield
        finally:
            if enable_scheduler:
                service.stop_scheduler()

    app = FastAPI(title="Job Search Tracker", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.post("/runs")
    def create_run(request: RunRequest | None = None) -> ListResponse:
        source_names = request.source_names if request else None
        started = service.start_run_background(source_names or None)
        return ListResponse(items=[{"status": "started" if started else "already_running"}])

    @app.get("/runs")
    def list_runs() -> ListResponse:
        return ListResponse(items=service.list_runs())

    @app.get("/runs/status")
    def run_status() -> dict:
        return service.run_status()

    @app.get("/jobs")
    def list_jobs(
        country: str | None = Query(default=None),
        application_status: str | None = Query(default=None),
        employer_class: str | None = Query(default=None),
        include_demo: bool = Query(default=False),
    ) -> ListResponse:
        return ListResponse(
            items=service.list_jobs(
                country=country,
                application_status=application_status,
                employer_class=employer_class,
                include_demo=include_demo,
            )
        )

    @app.get("/jobs/{job_id}")
    def get_job(job_id: int):
        job = service.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return job

    @app.patch("/applications/{job_id}")
    def patch_application(job_id: int, update: ApplicationUpdate):
        if not service.get_job(job_id):
            raise HTTPException(status_code=404, detail="Job not found")
        return service.update_application(job_id, update)

    @app.get("/filters")
    def list_filters():
        return service.list_filters()

    @app.get("/saved-searches")
    def list_saved_searches():
        return ListResponse(items=service.list_filters()["saved_searches"])

    @app.post("/saved-searches")
    def create_saved_search(search: SavedSearchCreate):
        return service.save_search(search)

    @app.get("/sources")
    def list_sources(
        include_demo: bool = Query(default=False),
        include_disabled: bool = Query(default=False),
    ):
        return ListResponse(items=service.list_sources(include_demo=include_demo, include_disabled=include_disabled))

    @app.post("/sources")
    def create_source(source: SourceConfigCreate):
        return service.create_source(source)

    @app.put("/sources/{source_name}")
    def update_source(source_name: str, source: SourceConfigCreate):
        return service.update_source(source_name, source)

    @app.get("/settings/search-profile")
    def get_search_profile():
        return service.get_search_profile()

    @app.put("/settings/search-profile")
    def update_search_profile(profile: SearchProfile):
        return service.update_search_profile(profile)

    return app
