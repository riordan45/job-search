# job-search

Local-first job discovery and review tool for ML-adjacent and broad software roles in Europe.

## Stack

- Backend: FastAPI + SQLite
- Frontend: React + Vite + TypeScript
- Python environment: `uv`

## Quick start

```bash
uv sync
uv run job-search-serve
```

The backend defaults to `http://127.0.0.1:38471`. Override it with `JOB_SEARCH_PORT` if needed.

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

The frontend defaults to `VITE_API_BASE=http://127.0.0.1:38471`.

## Useful commands

```bash
uv run --extra dev pytest
uv run job-search-cli run-once
uv run job-search-cli seed-demo
uv run job-search-cli show-sources
```

## Notes

- Source coverage is employer-first for reliability.
- The built-in registry now includes verified Greenhouse, SmartRecruiters, and Arbeitnow sources plus demo seeds.
- SQLite data is stored under `data/job_search.db`.
- The included company registry is a starting point and should be expanded over time.
- Add custom sources at runtime through `POST /sources`; they are stored in `data/company_targets.local.json`.
- Tune countries/keywords/exclusions through `GET/PUT /settings/search-profile`; overrides are stored in `data/profile.local.json`.
