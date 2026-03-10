from __future__ import annotations

import os

import uvicorn

from job_search.api import create_app


def run() -> None:
    port = int(os.getenv("JOB_SEARCH_PORT", "38471"))
    uvicorn.run(create_app(), host="127.0.0.1", port=port)
