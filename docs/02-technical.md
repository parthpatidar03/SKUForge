# SKUForge — Technical Architecture

*Living document. Every architectural decision and mechanism, with the "why".*

## Pipeline (per SKU)

```
SKUInput {mpn, brand, description}
   │
   ▼
Orchestrator (skuforge/orchestrator.py — sync state machine run in a thread,
              emits PipelineEvent objects to an asyncio.Queue → SSE)
   │
   ├─ 1. SCOUT (agents/scout.py)
   │     • call_web_search(): Responses API with tools=[{"type":"web_search"}]
   │     • gpt-5-mini gathers URLs + url_citation annotations
   │     • second pass: gpt-5-nano classifies each URL → manufacturer /
   │       distributor / marketplace / other, marks direct PDF links
   │     • sorted by source trust tier, capped at MAX_SOURCES_PER_SKU (5)
   │
   ├─ 2. CLASSIFIER (agents/classifier.py)
   │     • gpt-5-mini, strict json_schema with enum over category ids
   │     • output: {category, confidence, reasoning}
   │     • category selects an attribute template (taxonomy.py)
   │
   ├─ 3. EXTRACTOR (agents/extractor.py) — all sources in parallel
   │       (ThreadPoolExecutor; results replayed in trust order so the merged
   │        record is deterministic regardless of completion order)
   │     • cache.fetch(url): httpx GET → disk cache (sha256(url) key), one
   │       retry with doubled timeout; 401/403/429 recorded as "blocked" and
   │       not retried (the server answered — retrying won't help)
   │     • HTML: BeautifulSoup strips script/style/nav → text (40k char cap)
   │     • PDF: raw bytes → base64 data: URI → {"type":"input_file"} content
   │       part (native multimodal PDF parsing = the VLM capability)
   │     • strict schema: attributes restricted to the template's names (enum),
   │       each with {value, unit, quote}; also image_urls, certifications,
   │       equivalent_mpns
   │     • guardrails in prompt: "only report attributes explicitly present —
   │       never guess", exact supporting quote required
   │     • sources returning <200 chars of text treated as blocked/unusable
   │
   ├─ 4. VALIDATOR (agents/validator.py) — the Trust Engine, mostly deterministic
   │     • group evidence per attribute name across sources
   │     • fast path: exact match after normalization (lowercase value+unit)
   │     • subsumption merge: when one normalized value contains another
   │       (≥4 chars), they are the same fact at different detail levels
   │       ("AWG 14...AWG 8" vs "AWG 14...AWG 8 aluminium/copper; ...AWG 10
   │       copper") — merged, longer kept as canonical, NOT a conflict
   │     • slow path: gpt-5.6 (medium effort) judges equivalence groups —
   │       handles "0.5 in" vs "1/2\"" vs "12.7mm" (LLM used ONLY for
   │       equivalence judgment, never to invent values)
   │     • winner = largest agreement group; tie → highest source trust
   │     • status: verified (≥2 agreeing) / single-source / conflict
   │       (disagreement → losing values kept visible in conflicting_values)
   │     • cross-source lists: image URLs filtered to real image extensions
   │       (models hand back source PDFs as "images"); certifications and
   │       equivalent MPNs deduped case/whitespace-insensitively
   │     • confidence = 0.5·best_source_trust + 0.35·corroboration + 0.15·coverage
   │       - source trust: manufacturer 1.0, distributor 0.75, marketplace 0.5
   │       - corroboration: min(agreeing_sources/2, 1)
   │       - coverage: agreeing/total sources
   │       - conflicts hard-capped at 0.5 → can never auto-approve
   │
   └─ 5. COMPOSER (agents/composer.py)
         • gpt-5.6 (low effort) writes seo_title, short/long description,
           search synonyms
         • input = ONLY attributes with confidence ≥ 0.5 and non-conflict
           status → copy can't launder hallucinations into prose

Record status: auto-approved iff every attribute ≥ AUTO_APPROVE_THRESHOLD (0.8)
and no conflicts; else needs-review. Human review (approve/edit/reject per
attribute) promotes record → approved.
```

## Model routing (config.MODELS)

| Stage | Model | reasoning.effort | Rationale |
|---|---|---|---|
| scout | gpt-5-mini | low | web_search tool call, moderate volume |
| relevance | gpt-5-nano | minimal | URL classification, cheapest |
| classifier | gpt-5-mini | low | single enum pick |
| extractor | gpt-5-mini | low | schema does the heavy lifting; multimodal for PDFs |
| validator | gpt-5.6 | medium | highest-stakes judgment (equivalence) |
| composer | gpt-5.6 | low | customer-visible copy quality |

Cost tracked per call from token usage × price table (llm.PRICES), accumulated
onto the record (`cost_usd`) → powers the cost-per-SKU stat.

## Key design decisions & why

1. **No agent framework (LangChain/LangGraph).** The orchestration loop is
   ~100 lines of plain Python. Debuggable, no dependency churn, and a stronger
   "defend your architecture" story than framework glue.
2. **Deterministic trust math, LLM only for equivalence.** Confidence must be
   explainable to a judge in one sentence. An LLM-generated "confidence" would
   itself be a hallucination risk.
3. **Strict Structured Outputs everywhere.** `text.format = {type: json_schema,
   strict: true}` → zero JSON parse failures, attribute names constrained by
   enum to the category template → no schema drift.
4. **Evidence cache as a feature, not a hack.** sha256-keyed disk cache of every
   fetched page/PDF. Production pattern (catalog runs re-hit the same
   datasheets), also makes demos immune to site outages and bot-blocking.
5. **Mock mode (`SKUFORGE_MOCK=1` or missing API key).** llm.py swaps API calls
   for fixture JSONs (`fixtures/<MPN>/<stage>.json`); extractor fixtures keyed
   per-URL. Full pipeline + UI runs offline; pytest runs against it.
6. **SSE, not WebSockets.** One-directional event stream = EventSource on the
   frontend, StreamingResponse on the backend, no protocol overhead. Events are
   the same objects the orchestrator emits — the agent theatre is free.
7. **Threaded sync pipeline under async API.** Pipeline code stays simple
   synchronous Python; FastAPI wraps it with `asyncio.to_thread`, events cross
   the boundary via `loop.call_soon_threadsafe` onto an `asyncio.Queue`.
8. **Parallel extraction, deterministic merge.** Per-source extraction is
   fanned out across a thread pool (35% latency cut measured live: 134 s →
   87 s), but results are merged in trust order, so the same inputs always
   produce the same record regardless of which source returns first.
9. **Failure reasons are first-class.** A skipped source reports *why*
   (`blocked (403)`, `no readable text`, `ReadTimeout`). Manufacturer HTML
   pages are frequently bot-protected, so the system is designed to lean on
   their spec-sheet PDFs — Scout ranks PDFs first within each trust tier.
10. **Graceful degradation over all-or-nothing.** Enrichment is expensive and
    mostly front-loaded (fetching and extracting sources), so a late failure
    must not discard it. Three layers: a failed equivalence call falls back to
    deterministic bucketing (values differ → reported as a conflict, not lost);
    a failed composer leaves copy blank but keeps every attribute; any other
    late exception saves the record as `needs-review` with whatever was
    validated, reserving `failed` for runs that produced nothing. Verified by
    `tests/test_resilience.py`.

## Measured live performance (single SKU, cold cache)

| Metric | Value |
|---|---|
| Wall time | ~87 s |
| Cost | $0.022–0.027 (≈ ₹2) vs ₹150–250 manual |
| Sources found / usable | 5 / 3 (manufacturer HTML 403s; PDFs succeed) |
| Attributes produced | 12–13 |
| Genuine conflicts surfaced | 1–2 |

## API surface (skuforge/api.py)

| Endpoint | Purpose |
|---|---|
| `POST /api/enrich` | start pipeline for one SKU → `{record_id}` |
| `GET /api/events/{id}` | SSE stream of agent events (terminates with `done`) |
| `GET /api/records` | list summaries (incl. conflict counts) |
| `GET /api/records/{id}` | full record |
| `POST /api/records/{id}/review` | HITL: approve / edit / reject one attribute |
| `POST /api/batch` | CSV upload (mpn,brand,description) → parallel runs |
| `GET /api/stats` | throughput, auto-approval rate, avg cost/duration |
| `GET /api/export/{id}.csv` | syndication-ready flat export |

## Data model (skuforge/models.py)

`ProductRecord` = input + category(+confidence) + commerce copy + attributes +
synonyms/certs/images/datasheets/equivalent MPNs + sources + status + cost +
duration. `Attribute` = name/value/unit + confidence + status + evidence[]
(each: source_url, source_type, raw_value, exact quote) + conflicting_values[]
+ human_reviewed. Stored as JSON documents in SQLite (`records` table).

## Frontend (frontend/app/page.tsx — single-page dashboard)

- Stats bar: records, auto-approval %, avg cost/SKU, avg time, flagged attrs
- Input form → `POST /api/enrich` → EventSource on `/api/events/{id}`
- Agent theatre: color-coded per-agent log, auto-scrolling
- Attribute table: confidence bar (green/amber/red), status badges; row expands
  to evidence quotes + source links; conflict rows auto-expand and offer
  "use this value" (one-click resolve via review endpoint), approve/reject
- Side panels: commerce copy + synonyms chips; sources, certs, equivalents,
  cost/duration, CSV export link

## Testing

`backend/tests/test_pipeline.py` (mock mode): end-to-end record shape;
conflict flagged for weight_lbs with confidence ≤ 0.5 and losing values
retained; verified attribute requires ≥2 evidence with confidence ≥ 0.9.
