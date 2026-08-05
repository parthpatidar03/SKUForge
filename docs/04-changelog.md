# SKUForge — Build Log

*Chronological record of what was built, when, and why. Raw material for the LinkedIn post.*

## 5 Aug 2026 — Session 1: planning

- Grilled the problem statement into locked decisions (see `PLAN.md`).
- Background research agent profiled Unilog: their moat is a 10M-SKU content
  library built by **human** teams; their own AI product **HyperScale** (Oct
  2025) ships only descriptions/blogs/synonyms — item matching, grouping, and
  image agents are still "coming soon". Conclusion: build the trust layer none
  of them ship, on their own roadmap gap. Vertical chosen: **electrical**
  (public IDEA/UNSPSC attribute schemas, deep manufacturer datasheets,
  cross-checkable distributor listings).
- Differentiator locked: **Trust Engine** (per-attribute confidence +
  provenance + conflict detection) with a live **agent theatre** demo layer.

## 5 Aug 2026 — Session 2: skeleton built (≈1 hour)

Milestone planned for Aug 5-7 — completed on day 1.

**Verified against OpenAI docs before writing code:** flagship model is
**gpt-5.6** (plan originally assumed 5.1); Responses API provides built-in
`web_search` (so Tavily was dropped from the stack), strict Structured Outputs
via `text.format`, `reasoning.effort` levels including `minimal`, and native
PDF `input_file` parts (the vision-language capability, no extra infra).

Built, in order:
1. `config.py`, `models.py` — config + Pydantic contracts
2. `llm.py` — the single OpenAI boundary (structured / web-search calls, cost
   accounting, mock-mode fixture loading)
3. `cache.py` — sha256-keyed disk cache for pages and PDFs
4. `taxonomy.py` — 12 category attribute templates
5. Agents: `scout` → `classifier` → `extractor` → `validator` → `composer`
6. `store.py` (SQLite), `orchestrator.py` (state machine + events), `cli.py`
7. HOM230CP fixtures — a real Square D breaker across 4 sources, with a
   deliberate weight conflict (0.75 lbs manufacturer vs 1.1 lbs distributors)
8. `api.py` — FastAPI: enrich, SSE events, records, HITL review, batch CSV,
   stats, CSV export
9. `tests/test_pipeline.py` — 3 smoke tests (all passing)
10. `frontend/app/page.tsx` — full dashboard

**Bug caught during build:** `_group_values()` in the validator returned only
groups while the caller expected a cost too — fixed to return `(groups, cost)`
so validator LLM spend is tracked.

**Verified live in the browser (not just tests):** clicked Enrich → agent
theatre streamed all 14 pipeline events → record rendered with 11 attributes →
`weight_lbs` auto-expanded as a **conflict** at 50% confidence showing both
distributor quotes and the manufacturer's 0.75 lbs → clicked "use this value" →
attribute became **human-verified, 100%**. The HITL loop works end to end.

Commits: skeleton backend · .gitattributes · smoke tests · dashboard.

## 5 Aug 2026 — Session 3: documentation system

- Created `docs/` (this folder): `01-overview.md` (plain English + tech stack),
  `02-technical.md` (architecture, decisions, API, data model),
  `03-files.md` (file-by-file reference), `04-changelog.md` (this log).
- Standing rule adopted: **every future change updates these docs in the same
  session, without being asked.**
- Dev servers registered in `.claude/launch.json` as `skuforge-backend` (:8000)
  and `skuforge-frontend` (:3005).

## 5 Aug 2026 — Session 4: first live runs + hardening

API key added; `MOCK_MODE` off. Three live runs on the same Square D breaker,
each one exposing real-world failures the fixtures could never show.

**Run 1 — baseline (116 s, $0.0169, 11 attributes, 5 conflicts).**
Scout found 5 sources; only 2 were usable. Notably one of them was a spec sheet
hosted on **assets.unilogcorp.com — Unilog's own CDN** (a nice detail for the
demo: the system independently found the judges' own content). Problems found:

| Symptom | Diagnosis | Fix |
|---|---|---|
| 3 of 5 sources "unusable", no reason given | `se.com` product pages return **403** (bot protection); the CloudFront PDF was a **timeout** on a 536 KB file | `cache.fetch()` now retries once with a doubled timeout, distinguishes 401/403/429 as `blocked` (no retry — the server answered) from transient errors, and records the reason in `_FAILURES`; the pipeline event now reads `Skipped — blocked (403)` instead of a generic message |
| 5 conflicts from only 2 sources | Values like `AWG 14...AWG 8` vs `AWG 14...AWG 8 aluminium/copper)1; AWG 14...AWG 10 copper)2` are the *same fact at different detail*, not contradictions | added `_subsumes()` — buckets merge when one normalized value contains the other (≥4 chars), keeping the longer as canonical |
| `image_urls` contained PDF links | the model returned the source document URL as an "image" | `_is_image()` filters to real image extensions |
| certifications listed `UL listed` **and** `UL Listed` | no normalization | `_dedupe_labels()` collapses case/whitespace duplicates, keeps first spelling |
| manufacturer HTML blocked while its PDFs are open | HTML product pages are bot-protected; spec-sheet PDFs sit on open CDNs and are attribute-dense | Scout now sorts PDFs first *within* each trust tier and its prompt asks for at least two direct PDF links |

**Run 2 — after fixes (134.6 s, $0.0272).** 3 usable sources (CloudFront PDF now
succeeds), 13 attributes, conflicts down 5 → 2. Both survivors are *genuine*
disagreements a human should settle: two different GTINs, and weight 0.65 lb vs
1 lb (net vs shipping). Certifications deduped; no PDFs in images. Triple-
corroborated attributes reached 0.92 confidence.

**Parallel extraction.** Sources are independent, so the orchestrator now runs
extraction across them in a `ThreadPoolExecutor`, then replays results in trust
order so output stays deterministic. **Run 3: 87.3 s** — a 35% latency cut, and
the lever that makes catalog-scale batches practical.

### Current live numbers (single SKU, cold cache)
~87 s, **$0.022–0.027 per SKU (≈₹2)** versus ₹150–250 for manual enrichment;
12–13 attributes from 3 usable sources, 1–2 genuine conflicts surfaced for
human review.

## 5 Aug 2026 — Session 5: second category + resilience

**Cross-category test through the UI.** Ran a Leviton `1451-2W` switch from the
dashboard. Scout found 5 sources and **all 5 were usable** (2 manufacturer +
3 distributor, 51 raw attribute extractions — much richer than the breaker,
whose manufacturer pages 403'd). The classifier correctly routed it to the
**Switch (Wiring Device)** template rather than circuit_breaker, confirming the
category-aware schema generalizes. Live SSE streaming in the browser worked
throughout.

**The run then failed at 155 s.** Root cause was **not** a code defect: the
OpenAI account hit `credit_balance_exhausted` (HTTP 429) partway through the
validator's equivalence calls. Three real problems surfaced anyway:

| Problem | Fix |
|---|---|
| The API layer swallowed the exception (`except Exception: pass`), so the traceback never reached the server log — the failure was invisible | `logger.exception()` in `api.py`; failures are now logged with record id and MPN |
| A late failure discarded **everything**, including 51 successful extractions and all validated attributes | orchestrator now keeps partial work: on a late exception the record is saved as `needs-review` with its attributes intact, and only marked `failed` if nothing was validated |
| One failed equivalence call could sink the whole validation pass | `_group_values()` falls back to deterministic buckets on API error — differing values are reported as a conflict for a human instead of being lost |

Composer failures are handled separately: validated attributes are the
expensive part of the pipeline, so copywriting is wrapped in its own try and a
failure there just leaves the copy fields blank and flags the record for review.

Added `tests/test_resilience.py` — asserts attributes survive a composer failure
and that an early (scout) failure still marks the record failed. **Suite: 5 tests
passing.**

### Blocked
**The OpenAI account has no credits remaining.** Add credits at
platform.openai.com to resume live runs. Total spend across all live runs so far
was about **$0.11**. Mock mode (`SKUFORGE_MOCK=1`) still runs the full pipeline
and the entire UI offline.

## 5 Aug 2026 — Session 6: vendor independence (free-tier path)

OpenAI credits ran out and buying more wasn't wanted, so the pipeline became
**provider-pluggable**. `llm.py` was already the only module touching a vendor,
so this cost no changes to any agent — the dispatch lives entirely inside it.

- `config.MODEL_ROUTING` now holds a per-stage table **per provider**, selected
  by `SKUFORGE_PROVIDER=openai|gemini`.
- Gemini path (`google-genai` SDK): `response_schema` for structured output,
  `Tool(google_search=GoogleSearch())` for grounding — citations read out of
  `grounding_metadata.grounding_chunks[].web.uri/title`, the same
  `{url, title}` shape the OpenAI path produces — and `inline_data` for PDF
  vision.
- `_sanitize_schema()` strips the JSON Schema keywords Gemini's OpenAPI-subset
  dialect rejects (`additionalProperties`, `min/maxLength`, `minimum`,
  `maximum`, `strict`), so agents keep authoring **one** schema for both.
- OpenAI-shaped file content parts are translated to Gemini `inline_data` at
  the boundary.

**Why Gemini specifically:** the pipeline needs three capabilities — web
grounding with citations, PDF/vision parsing, and schema-constrained JSON — and
Gemini's free tier covers all three. Its one restriction (a response schema and
the search tool cannot be combined in a single call) costs nothing here,
because `call_structured()` and `call_web_search()` were already separate.

Verified without spending anything: provider switch selects the Gemini routing
table, the sanitizer removes `additionalProperties` while keeping `enum`/
`required`, and the SDK imports. Suite still 5 passing.

**Architecturally this is worth more than the money it saves** — "swap the model
vendor with one environment variable" is a direct answer to a judge asking how
the design avoids lock-in.

## 5 Aug 2026 — Session 7: running free on Gemini, and a trust-engine bug

Switched to a Gemini key and ran the Leviton switch. Getting there took three
attempts, each teaching something.

**Model availability had to be probed, not assumed.** `gemini-2.5-flash-lite`
returns 404 ("no longer available to new users"), and `gemini-2.0-flash`,
`gemini-2.5-pro` and the whole 3.x range return 429 `RESOURCE_EXHAUSTED` on a
free key. Only **`gemini-2.5-flash`** has free quota, so every stage routes to
it and the stages are separated by *thinking budget* rather than by model size.
Lesson recorded because it will bite again: list and probe models against the
actual key instead of trusting a docs table.

**Free tiers rate-limit by the minute**, so firing five extractions at once
caused self-inflicted 429s. Added `_with_retry()` — exponential backoff with
jitter, and deliberately *no* retry for quota exhaustion (`insufficient_quota`),
since waiting cannot fix a spent balance. Extraction fan-out is now capped per
provider (`MAX_PARALLEL_EXTRACTIONS`: 3 on Gemini, 5 on OpenAI).

### The important find: single-source values were auto-approving

The first successful Gemini run returned `auto-approved` off **one** source.
The confidence blend was `0.5·trust + 0.35·corroboration + 0.15·coverage`, so a
lone manufacturer source scored `0.5 + 0.175 + 0.15 = 0.825` — over the 0.8
threshold. High source trust alone was clearing the bar with nothing
corroborating it, which is precisely the failure this project exists to
prevent.

Fixed with a hard rule rather than a re-weighting: **a value found in exactly
one source is capped at `SINGLE_SOURCE_CEILING` (0.75) and always goes to a
human**, however authoritative that source is. Locked in by
`test_single_source_never_auto_approves`.

### Three more defects from the same run

| Symptom | Cause | Fix |
|---|---|---|
| Evidence links pointed at `vertexaisearch.cloud.google.com/grounding-api-redirect/…` | Gemini grounding returns redirector URLs, so provenance cited Google instead of the real page | `cache` records the post-redirect `final_url`; the extractor rewrites the source to cite where it landed — links are now `leviton.com`, `zoro.com` |
| `400 INVALID_ARGUMENT: The document has no pages` | URLs that *look* like PDFs are often HTML redirects, but were sent to the model as PDFs | served content type decides `is_pdf`, overriding the classifier's guess |
| Free run reported a cost of $0.0251 | Gemini models were missing from `PRICES`, so the default rate applied | Gemini entries priced at zero |

### Result — Leviton 1451-2W, entirely free

10 attributes in 115 s at **$0.00**. Sources cited: `leviton.com/assets/PDS/
1451-2W.pdf`, `leviton.com/en/products/1451-2w`, `zoro.com`, plus a distributor
spec sheet. Five attributes verified at 1.00 (amperage, colour, country of
origin, UPC, wiring type), four capped at 0.75 as single-source, and one genuine
conflict surfaced — `switch_type`: "Toggle Switch" (manufacturer) vs "Single
Pole Toggle AC Quiet" (distributor). Status `needs-review`, correctly.

The category-aware schema also proved itself: this record carries `colour`,
`wiring_type` and `number_of_gangs` — switch attributes that do not exist on the
breaker template.

### Still pending
- Category template tuning across more verticals
- Batch dashboard UI (backend endpoints already exist)
- Images: PDFs yield no image URLs — needs a distributor-page or image-search path
- Deploy (Vercel + Railway/Render), demo video, one-pager deck
