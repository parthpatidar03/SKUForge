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

- **Backend:** Python + FastAPI, hand-rolled async orchestration (no agent framework — the loop is 100 lines and debuggable). SSE streams live agent events to the UI. Per-source extraction runs in parallel, merged deterministically in trust order.
- **LLM: provider-pluggable.** The pipeline needs three capabilities — grounded web search with citations, PDF/image parsing, schema-constrained JSON — and both OpenAI (Responses API) and Google Gemini (`google-genai`) supply all three. `SKUFORGE_PROVIDER=openai|gemini` swaps vendors; no agent code changes, because `llm.py` is the only module that touches an SDK. **Gemini's free tier runs the whole system at zero cost.** Model routing per stage (cheap tier → flagship) keeps paid runs at pennies per SKU.
- **Evidence cache:** every fetched page/PDF cached on disk — no re-fetching across a catalog run.
- **Storage:** SQLite (records as JSON documents).
- **Mock mode:** `SKUFORGE_MOCK=1` runs the full pipeline against fixtures, zero API calls.

## Run it

```bash
cd backend
pip install -r requirements.txt
copy .env.example .env   # set SKUFORGE_PROVIDER and the matching API key
python -m skuforge.cli HOM230CP "Square D" "30A 2 pole breaker"   # terminal run
uvicorn skuforge.api:app --reload --port 8000                     # API server
```

Free path: get a key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey), then set `SKUFORGE_PROVIDER=gemini` and `GEMINI_API_KEY=...`.
With no key at all, `SKUFORGE_MOCK=1` runs the entire pipeline and UI offline against recorded fixtures.

Key endpoints: `POST /api/enrich` · `GET /api/events/{id}` (SSE) · `GET /api/records` · `POST /api/records/{id}/review` (HITL) · `POST /api/batch` (CSV) · `GET /api/stats` · `GET /api/export/{id}.csv`

## Status

- [x] Five-agent pipeline, end-to-end (mock + live paths)
- [x] Trust engine: confidence, provenance, conflict detection
- [x] FastAPI + SSE + HITL review + batch + stats + CSV export
- [ ] Next.js dashboard (record view, agent theatre, review queue, batch stats)
- [ ] Live-key validation run + category template tuning
- [ ] Deploy (Vercel + Railway), demo video
