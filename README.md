# SKUForge

**Turn `MPN + brand + one-line description` into complete, commerce-ready product records — where every attribute carries a confidence score, clickable evidence, and cross-source conflict detection.**

Built solo for **UniHack 2026** (Unilog AI Hackathon).

## The problem

B2B distributors receive supplier feeds with a part number, a brand, and maybe one line of text. Turning that into a sellable catalog record (specs, taxonomy, SEO copy, images, certifications) is done today by human content teams — slow, expensive, and unscalable across 100k+ SKU catalogs. Naive LLM enrichment is worse: hallucinated industrial specs cause wrong orders.

## The answer: enrichment you can trust

SKUForge runs a five-agent pipeline per SKU:

```
input (MPN, brand, one-liner)
  → SCOUT       finds evidence: manufacturer pages, PDF datasheets, distributor listings
  → CLASSIFIER  picks a category-specific attribute template (IDEA/UNSPSC-style)
  → EXTRACTOR   pulls attributes per source, with exact supporting quotes (HTML + PDF vision)
  → VALIDATOR   cross-merges sources: confidence scoring, unit-aware equivalence,
                explicit CONFLICT flagging — never silently picks a winner
  → COMPOSER    writes SEO title, descriptions, search synonyms from verified facts only
```

Every attribute ends up `verified` (2+ agreeing sources), `single-source`, `conflict` (both values shown, human decides), or `generated` — with per-attribute confidence and provenance quotes. Records auto-approve above a confidence threshold; only flagged attributes hit the human review queue.

## Architecture

- **Backend:** Python + FastAPI, hand-rolled async orchestration (no agent framework — the loop is under 150 lines and debuggable). SSE streams live agent events to the UI. Per-source extraction runs in parallel, merged deterministically in trust order.
- **LLM: provider-pluggable, capability-routed.** The pipeline needs three capabilities — grounded web search with citations, PDF/image parsing, schema-constrained JSON. `SKUFORGE_PROVIDER` selects a profile: `openai`, `gemini`, `openrouter`, or **`hybrid`** (default) — Gemini's free tier handles only search and PDF vision, every text-only stage runs on free OpenRouter models. No agent code changes between profiles, because `llm.py` is the only module that touches a vendor SDK. **The hybrid profile runs the whole system at $0.00/SKU.**
- **Frontend:** Next.js + Tailwind — single-SKU form, live agent-theatre panel (SSE), trust panel with per-attribute confidence bars and evidence quotes, HITL review/conflict-resolution UI, catalog table, CSV batch upload.
- **Evidence cache:** every fetched page/PDF cached on disk — no re-fetching across a catalog run.
- **Storage:** SQLite (records as JSON documents).
- **Mock mode:** `SKUFORGE_MOCK=1` replays the pipeline against fixtures snapshotted from real runs — zero API calls, same sources/values/conflicts as the live enrichment they came from.

## Run it

```bash
cd backend
pip install -r requirements.txt
copy .env.example .env   # set SKUFORGE_PROVIDER + keys (hybrid is free — see below)
python -m skuforge.cli HOM230CP "Square D" "30A 2 pole breaker"   # terminal run
uvicorn skuforge.api:app --reload --port 8000                     # API server

cd ../frontend
npm install
npm run dev   # dashboard at localhost:3005 (NEXT_PUBLIC_API_URL if backend isn't on :8000)
```

**Recommended free path:** `SKUFORGE_PROVIDER=hybrid` with a free key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey) (`GEMINI_API_KEY`) and [openrouter.ai/keys](https://openrouter.ai/keys) (`OPENROUTER_API_KEY`). With no keys at all, `SKUFORGE_MOCK=1` runs the entire pipeline and UI offline against recorded fixtures.

Catalog-scale: `python -m skuforge.batch sample_batch.csv` — resumable, bounded concurrency, prints a throughput/cost/quality summary.

Key endpoints: `POST /api/enrich` · `GET /api/events/{id}` (SSE) · `GET /api/records` · `POST /api/records/{id}/review` (HITL) · `POST /api/batch` (CSV) · `GET /api/stats` · `GET /api/export/{id}.csv`

## Status

- [x] Five-agent pipeline, end-to-end (mock + live, verified on real websites)
- [x] Trust engine: confidence, provenance, conflict detection, single-source cap
- [x] FastAPI + SSE + HITL review + batch + stats + CSV export
- [x] Next.js dashboard: record view, agent theatre, review queue, catalog + batch upload
- [x] Zero-cost hybrid provider (Gemini + OpenRouter free tiers)
- [x] Offline fixture replay, pinned to real recorded runs by automated tests
- [x] Deploy configs ready (`backend/Dockerfile`, `railway.json`, `Procfile`); frontend deployable via Vercel
- [ ] Full 10-SKU demo catalog (free-tier daily quota paces this a few SKUs/day)
- [ ] Demo video
