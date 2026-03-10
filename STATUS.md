# Status

## What Is Done

- Built a local-first job search app with:
  - FastAPI backend
  - SQLite persistence
  - React/Vite frontend
  - `uv`-managed Python environment
- Added ingestion, normalization, dedupe, ranking, and application tracking.
- Added strict geography filtering so only `Germany`, `Switzerland`, `Netherlands`, and `Romania` are kept active.
- Added source-trust prioritization:
  - direct company pages rank above hosted ATS pages
  - hosted ATS pages rank above aggregators
  - lower-trust duplicates do not overwrite higher-trust copies
- Fixed stale refresh-state handling in the backend/frontend.
- Removed demo jobs from normal production listings so fake links do not show up in the main inbox.
- Reworked the frontend away from the earlier bad review layout into a more usable inbox + detail pane.

## Implemented Scrapers

### Direct company adapters

- `Google`
  - official Google Careers results pages
  - official Google job detail pages
- `Apple`
  - official Apple jobs search hydration payload
  - official Apple detail URLs
- `NVIDIA`
  - official NVIDIA Workday endpoint
- `Amazon`
  - official `amazon.jobs` search API
  - official country filter using `normalized_country_code[]`
  - official job URLs on `amazon.jobs`

### ATS / platform adapters

- `Greenhouse`
- `Lever`
- `SmartRecruiters`
- `Workday`

### Aggregator / supplemental adapters

- `Arbeitnow`

## Live Source Coverage Added

The registry now includes these real sources:

- `google`
- `amazon`
- `apple`
- `nvidia`
- `stripe`
- `datadog`
- `mongodb`
- `elastic`
- `cloudflare`
- `adyen`
- `n26`
- `imc`
- `delivery-hero`
- `remote`
- `contentful`
- `getyourguide`
- `celonis`
- `bitpanda`
- `truelayer`
- `flow-traders`
- `wayve`
- `commercetools`
- `spryker`
- `mirakl`
- `sumup`
- `figma`
- `intercom`
- `gitlab`
- `arbeitnow-de`

## Verified So Far

- Python tests are passing.
- Frontend build was passing at the last verification point.
- Real ingestion has already produced large live result sets.
- The Amazon adapter was live-probed against the official endpoint and returned real jobs in:
  - `Berlin`
  - `Bucharest`
  - `Iasi`
  - `Zurich`
  - `Amsterdam`

## Known Limitations

- New Python adapter code requires a backend restart. Config-only changes can be picked up more easily, but new adapter classes are not hot-loaded into an already-running server.
- Some direct-company adapters still use listing payloads without a second detail-page fetch when the official endpoint already exposes enough structured data.
- Source coverage is good but still incomplete for top-priority direct-company pages.
- There is not yet any application automation, autofill, or browser-driving.
- The frontend is functional, not polished.

## What Is Left To Do

### High priority

- Add more direct-company adapters for high-value targets:
  - `Meta`
  - `Microsoft`
  - `OpenAI` if publicly usable
  - `Palantir`
  - `Booking.com`
  - `Uber`
  - `Snowflake`
  - `DeepMind` / Alphabet-adjacent sources where feasible
- Expand finance-heavy direct sources for the Netherlands and broader Europe:
  - `Optiver`
  - `Jane Street`
  - `Citadel`
  - `Hudson River Trading`
  - `Jump Trading`
  - `Tower Research`
  - `Flow Traders` direct if an official feed is available beyond the current source

### Scraper quality

- Prefer direct company pages over third-party ATS URLs whenever the company has a stable official public endpoint.
- Add company-specific detail-page fetches where the search/listing payload is too shallow.
- Expand adapter-specific parsing for:
  - structured locations
  - multilingual postings
  - posted dates
  - employment type / remote mode
- Keep tightening false-positive filtering for mixed-location or ambiguous global postings.

### Product / UX

- Improve the frontend density and keyboard navigation for reviewing jobs quickly.
- Hide low-value operational UI until needed.
- Make run progress clearer while a scrape is active.
- Add better source management in the UI for enabling/disabling sources and editing priorities.

### Later, not now

- Automated application workflows
- Resume / cover-letter artifact management
- Browser automation for form filling
- Hosted or multi-user deployment

## Immediate Next Recommended Steps

1. Add `Meta` direct adapter.
2. Add `Microsoft` direct adapter.
3. Add more direct finance-company sources.
4. Improve the review UI density once source coverage is broader.
