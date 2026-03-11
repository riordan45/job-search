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
- Added source quality reporting and source enable/disable support in the backend and frontend.
- Added stricter role parsing for:
  - `software engineer`
  - `ml engineer`
  - `applied scientist`
  - `research engineering`
  - `forward deployment`
- Removed demo jobs from normal production listings so fake links do not show up in the main inbox.

## Implemented Scrapers

### Direct company adapters

- `Google`
  - official Google Careers results pages
  - official Google job detail pages
- `Apple`
  - official Apple jobs search hydration payload
  - official Apple detail URLs
- `Amazon`
  - official `amazon.jobs` search API
  - official country filter using `normalized_country_code[]`
  - official job URLs on `amazon.jobs`
- `NVIDIA`
  - official `jobs.nvidia.com` Eightfold careers API
  - official NVIDIA position detail endpoint
- `Microsoft`
  - official `apply.careers.microsoft.com` Eightfold careers API
  - target-country search for `CH`, `DE`, `NL`, `RO`
- `Booking.com`
  - official `jobs.booking.com/api/jobs`
  - target-country search for `CH`, `DE`, `NL`, `RO`
- `Revolut`
  - official `revolut.com/careers` `__NEXT_DATA__` payload
  - official position pages fetched through Cloudflare-aware client
  - target-country filtering for `CH`, `DE`, `NL`, `RO`
- `Uber`
  - official `uber.com` careers RPC endpoints:
    - `POST /api/loadFilterOptions`
    - `POST /api/loadSearchJobsResults`
  - official job detail URLs under `/global/en/careers/list/<id>/`
  - target-country filtering for `CH`, `DE`, `NL`, `RO`
- `Wise`
  - official `wise.jobs` pages with structured job payload extraction
- `Zalando`
  - official `jobs.zalando.com` embedded data payload

### ATS / platform adapters

- `Greenhouse`
- `Lever`
- `SmartRecruiters`
- `Workday`
- `Ashby`
- `Eightfold`

### Aggregator / supplemental adapters

- `Arbeitnow`
  - still supported
  - disabled by default because it is low-yield / noisy for the target profile

## Live Source Coverage In Registry

The built-in registry now includes these real sources:

- `asml`
- `arbeitnow-de`
- `google`
- `meta`
- `microsoft`
- `booking`
- `spotify`
- `jane-street`
- `deepmind`
- `revolut`
- `uber`
- `amazon`
- `stripe`
- `apple`
- `datadog`
- `mongodb`
- `elastic`
- `cloudflare`
- `adyen`
- `n26`
- `imc`
- `delivery-hero`
- `remote`
- `nvidia`
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
- `databricks`
- `palantir`
- `snowflake`
- `openai`
- `checkout`
- `mollie`
- `wise`
- `zalando`

## Verified So Far

- Python tests are passing.
- Frontend build is passing.
- Real live probes have been run against the new direct-company sources.

Live probe snapshots from March 11, 2026:

- `ASML`
  - direct source implemented from official `job_posting-sitemap.xml` plus public job-page `__NEXT_DATA__`
  - sampled `120` official pages
  - retained `16` target-country jobs in the sample
  - observed current matches in `Netherlands` (`Veldhoven`, `Delft`)
- `Meta`
  - current live coverage returned `14` target-country listings
  - observed current matches in `Germany` and `Switzerland`
- `Spotify`
  - current live coverage returned `2` target-country listings
  - observed current matches in `Germany`
- `Jane Street`
  - official live feed currently returns `0` jobs after the `CH/DE/NL/RO` filter
  - current live office set in the official feed did not include active `Germany`, `Netherlands`, `Romania`, or `Switzerland` openings
- `Microsoft`
  - discovered `86` jobs
  - country split:
    - `CH`: `22`
    - `DE`: `27`
    - `NL`: `28`
    - `RO`: `18`
- `Booking.com`
  - discovered `93` jobs
  - country split:
    - `DE`: `2`
    - `NL`: `75`
    - `RO`: `16`
- `Revolut`
  - discovered `162` target-country jobs
  - country split:
    - `CH`: `13`
    - `DE`: `11`
    - `NL`: `6`
    - `RO`: `128`
- `Uber`
  - discovered `18` filtered jobs after country + coarse role filtering
  - country split:
    - `CH`: `0`
    - `DE`: `0`
    - `NL`: `18`
    - `RO`: `0`

## Known Limitations

- New Python adapter code requires a backend restart. Config-only changes are easier to pick up, but new adapter classes are not hot-loaded into an already-running server.
- Some company sites are now using Cloudflare or similar protections, so scraping may require a browser-like HTTP client.
- `Revolut` currently does not expose a posted date in the source payload used here, so `posted_at` stays empty there.
- `Uber` has a good official API, but broad searches can still leak non-tech jobs; the current adapter uses tighter role filtering and now trends heavily toward Amsterdam-based technical roles.
- `Romania` currently appears absent in Uber’s official target-country results for the implemented query set.
- There is not yet any application automation, autofill, or browser-driving.
- The frontend is functional, not polished.

## High-Value Sources Added Since The Earlier Version

- `ASML`
- `DeepMind`
- `Meta`
- `Spotify`
- `Jane Street`
- `Microsoft`
- `Booking.com`
- `Revolut`
- `Uber`
- `Databricks`
- `Palantir`
- `Snowflake`
- `OpenAI`
- `Checkout.com`
- `Mollie`
- `Wise`
- `Zalando`

## Not Added Yet

These are still not implemented as first-class sources:

- `SAP`
- `JetBrains`
- `Picnic`
- `Klarna`
- `Thought Machine`
- `Worldline`
- `Citadel`
- `Hudson River Trading`
- `Jump Trading`
- `Tower Research`

## Remaining Target Company Tracker

Done:

- `ASML`
- `DeepMind`
- `Meta`
- `Spotify`
- `Jane Street`

Still to implement:

- `SAP`
- `JetBrains`
- `Picnic`
- `Klarna`
- `Thought Machine`
- `Worldline`
- `Citadel`
  - official `career-sitemap.xml` is reachable
  - official detail pages under `/careers/details/.../` are Cloudflare-blocked from this environment, so location-safe parsing is not implemented yet
- `Hudson River Trading`
- `Jump Trading`
- `Tower Research`

## Today’s Session

- Added `DeepMind` as a first-class source.
- Added `Meta` as a direct-company adapter using Meta’s public careers bootstrap plus GraphQL search and job-page JSON-LD normalization.
- Added `Spotify` as a direct-company adapter using Spotify’s public jobs API plus official job-page payloads.
- Added `Jane Street` as a direct-company adapter using Jane Street’s public JSON feeds and official position URLs.
- Added `ASML` as a direct-company adapter using ASML’s official job sitemap plus job-page `__NEXT_DATA__`.
- Extended regression coverage for the new adapters and source registry entries.
- Verified the full Python test suite is passing.

## What Is Left To Do

### High priority

- Add the remaining direct-company sources where an official scrapeable surface can be verified:
  - `SAP`
  - `JetBrains`
  - `Picnic`
  - `Klarna`
  - `Thought Machine`
  - `Worldline`
- Add the remaining finance-heavy targets only through official endpoints that still preserve the hard country filter:
  - `Citadel`
  - `Hudson River Trading`
  - `Jump Trading`
  - `Tower Research`

### Scraper quality

- Keep tightening false-positive filtering for mixed-location or ambiguous global postings.
- Improve adapter-specific parsing for:
  - structured locations
  - posted dates
  - employment type / remote mode
  - multilingual postings
- Keep preferring direct company pages over ATS or aggregators whenever a stable official endpoint exists.

### Product / UX

- Improve frontend density and keyboard navigation for fast triage.
- Add better source sorting/filtering by yield and success rate.
- Make run progress clearer while a scrape is active.

### Later, not now

- Automated application workflows
- Resume / cover-letter artifact management
- Browser automation for form filling
- Hosted or multi-user deployment

## Immediate Next Recommended Steps

1. Try `Klarna` next, because it is the most likely remaining target to fit an existing ATS adapter cleanly.
2. Try `SAP` or `JetBrains` after that, depending on which official careers surface is easier to verify from this environment.
3. Leave `Citadel` blocked until an official, non-Cloudflare-blocked detail or API surface is found.
4. After the remaining high-value targets are in, tighten relevance filtering further using live source metrics.
