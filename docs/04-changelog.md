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

### Still pending
- Live API-key run (needs `backend/.env` + a spend cap on the key)
- Category template tuning against real extraction results
- Batch dashboard UI (backend endpoints already exist)
- Deploy (Vercel + Railway/Render), demo video, one-pager deck
