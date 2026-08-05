# SKUForge — File-by-File Reference

*Living document. Every file, what it does, why it exists.*

## backend/

### `requirements.txt`
openai (Responses API), fastapi + uvicorn (API/SSE), pydantic (schemas),
python-dotenv (env), httpx (evidence fetching), beautifulsoup4 (HTML → text).

### `.env.example` / `.gitignore`
`OPENAI_API_KEY`, `SKUFORGE_MOCK` toggle. Git ignores `.env`, `cache/`,
`skuforge.db`, `__pycache__`, `.venv`.

### `sample_batch.csv`
10-row demo catalog (9 electrical + 1 plumbing valve for the cross-vertical
proof) for `POST /api/batch`.

## backend/skuforge/

### `config.py`
Single source of truth: loads `.env`; `PROVIDER` (`openai`|`gemini`) and the
matching API key; `MOCK_MODE` (explicit flag **or** missing key for the active
provider); paths (cache dir, SQLite, fixtures); `MODEL_ROUTING` — a per-stage
model + effort table **per provider**, with `MODELS` resolving to the active
one; `AUTO_APPROVE_THRESHOLD = 0.8`; `SOURCE_TRUST` tiers (manufacturer 1.0 →
other 0.4); fetch limits.

### `models.py`
Pydantic types shared by pipeline, API, and frontend contract:
`SKUInput`, `Source`/`SourceType`, `Evidence` (url + type + raw value + quote),
`Attribute` (+confidence, `AttributeStatus`, evidence[], conflicting_values[],
human_reviewed), `ProductRecord` (+`RecordStatus`, cost, duration),
`PipelineEvent` (agent, step, detail — the SSE payload).

### `llm.py`
Only file that talks to a model vendor, and the seam that makes the pipeline
provider-agnostic. Two public calls: `call_structured()` (schema-constrained
JSON, optional PDF/image parts) and `call_web_search()` (grounded free text +
`{url, title}` citations). Each dispatches on `config.PROVIDER` to an
OpenAI implementation (Responses API: `text.format` json_schema,
`tools=[web_search]`, `url_citation` annotations) or a Gemini one
(`google-genai`: `response_schema`, `Tool(google_search=GoogleSearch())`,
citations from `grounding_metadata.grounding_chunks`, PDFs as `inline_data`).
`_sanitize_schema()` strips JSON Schema keywords Gemini rejects so agents write
one schema for both. Both paths short-circuit to fixtures in mock mode.
`PRICES` + `_cost()` compute per-call USD from token usage (Gemini free tier
priced at zero).

### `cache.py`
Disk evidence cache. `fetch()` = cache-or-download (httpx, browser UA,
redirects) writing `<sha256>.meta.json` + `<sha256>.body`, with one retry at
doubled timeout for large datasheet PDFs; 401/403/429 are recorded as
`blocked` and never retried. `last_failure(url)` exposes the reason so the
pipeline can report *why* a source was skipped. `get()` for cache-only lookups;
`read_text()` strips scripts/nav via BeautifulSoup and caps at 40k chars.
PDFs bypass text extraction — they go to the model as files.

### `taxonomy.py`
12 category templates (circuit_breaker, contactor, switch, receptacle,
luminaire, wire_cable, motor, transformer, relay, conduit_fitting,
plumbing_valve, generic) each listing its expected attribute names —
IDEA/UNSPSC-style. Plus `UNIVERSAL_ATTRIBUTES` (upc_gtin, country_of_origin,
warranty, weight_lbs) applied to every product.

### `store.py`
SQLite persistence: `records(id, status, created_at, doc)` with the record
serialized as JSON. `save()` / `get()` / `list_all()`.

### `orchestrator.py`
The state machine: runs Scout → Classifier → Extractor (all sources in parallel
via `ThreadPoolExecutor`, results replayed in trust order for determinism) →
Validator → Composer, accumulating cost, emitting a `PipelineEvent` at every
step, deciding final status (auto-approved vs needs-review), always persisting
the record in `finally`. `_fixture_key()` maps an MPN to its fixture folder in
mock mode.

### `cli.py`
`python -m skuforge.cli MPN BRAND [DESC]` — terminal run printing the live agent
log then the full record JSON. Fastest way to test the pipeline without the UI.

### `batch.py`
`python -m skuforge.batch <csv> [limit]` — the catalog-scale path. Runs a CSV of
bare SKUs through the pipeline with `BATCH_CONCURRENCY` workers and prints a
summary: SKUs completed, wall time and time per SKU, total and per-SKU cost,
attributes generated, auto-approval rate, and the share of fields needing human
review. Abandons remaining SKUs on `QuotaExhausted` rather than repeating the
same failure.

### `prune.py`
`python -m skuforge.prune [--apply]` — demo hygiene. Development leaves the
store full of repeated runs of one SKU and failed attempts, which distorts the
catalog view and every aggregate. Keeps the best record per MPN (most
attributes, newest as tiebreak), drops the rest. Dry-run by default; `--apply`
copies the database to `skuforge.db.bak` first, so it is always reversible.

### `api.py`
FastAPI app + CORS. Runs the sync pipeline via `asyncio.to_thread`, bridging
events into a per-record `asyncio.Queue` (`loop.call_soon_threadsafe`) consumed
by the SSE endpoint. Endpoints: enrich, events, records list/detail, review
(HITL approve/edit/reject + record promotion), batch CSV, stats, CSV export.

## backend/skuforge/agents/

### `scout.py`
Two-stage source discovery: web_search prompt naming manufacturer page,
datasheet PDF, and distributor listings (explicitly asking for at least two
direct PDF links) → then a nano-model pass classifying URLs into trust tiers and
PDF flags. Returns top-N sources sorted by trust, **PDFs first within each
tier** — manufacturer HTML pages are routinely bot-blocked while their
spec-sheet PDFs sit on open CDNs.

### `classifier.py`
One structured call: MPN + brand + description → category enum + confidence +
reasoning. Enum is generated from `taxonomy.category_ids()` so the schema and
templates can never drift apart.

### `extractor.py`
Per-source extraction. Builds the strict schema dynamically from the category
template (attribute `name` is an enum of allowed names). HTML path feeds cached
text; PDF path attaches base64 `input_file`. Returns
`(extraction | None, cost, skip_reason)` — a named reason for blocked/empty
sources so the pipeline degrades visibly instead of failing silently.

### `validator.py`
Trust Engine. `_norm()` normalization + bucketing; `_subsumes()` merges buckets
where one value is the other plus qualifiers; `_group_values()` fast exact path,
LLM equivalence grouping only on remaining textual mismatch; `_confidence()`
weighted blend (source trust / corroboration / coverage); winner selection with
trust-based tie-break; status assignment and conflict capping. Merges image URLs
(filtered by `_is_image()` — models return source PDFs as images),
certifications and equivalent MPNs (`_dedupe_labels()` collapses
`UL listed`/`UL Listed`).

### `composer.py`
Commerce copy from verified facts only (confidence ≥ 0.5, non-conflict).
Structured output: seo_title, short_description, long_description,
search_synonyms. Prompt forbids inventing specs.

## backend/fixtures/HOM230CP/
`scout.json`, `relevance.json`, `classifier.json`, `extractor.json`
(keyed per source URL, with a `default`), `composer.json` — a realistic Square D
breaker enriched from 4 sources, deliberately containing a **weight conflict**
(manufacturer 0.75 lbs vs distributors 1.1 lbs) so the trust engine has
something real to flag in tests and demos.

## backend/tests/
`test_pipeline.py` — end-to-end run, conflict detection assertions, verified
status requiring 2+ evidence.
`test_resilience.py` — validated attributes survive a composer/API failure
(record becomes `needs-review`, not `failed`); an early scout failure still
marks the record `failed`.

## frontend/
Next.js 15 App Router + Tailwind, TypeScript.

### `app/page.tsx`
The entire dashboard: types mirroring the backend models; `ConfidenceBar`;
`AttributeRow` (expandable evidence, conflict panel with one-click resolve,
approve/reject); `Home` (stats bar, input form, EventSource wiring for the agent
theatre, record view, commerce copy + sources side panels, CSV export).

### `app/layout.tsx`
Metadata (title "SKUForge"), fonts, root shell.

## Repo root
- `PLAN.md` — hackathon battle plan: locked decisions, timeline, demo script, risks
- `README.md` — public-facing project readme (problem, architecture, how to run)
- `unilog-research.md` — research on Unilog's business, pain points, and the
  gap in their HyperScale product this project targets
- `.claude/launch.json` — dev server definitions
- `docs/` — this documentation set
