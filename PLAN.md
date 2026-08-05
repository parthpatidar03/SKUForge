# SKUForge — UniHack 2026 Battle Plan

**One-liner:** Turn `MPN + brand + one-line description` into a complete, commerce-ready product record where **every attribute carries a confidence score and clickable evidence** — and conflicts between sources are detected, not hallucinated over.

**Hackathon:** UniHack by Unilog · Submit by **23 Aug 2026** (buffer: submit 22 Aug) · Evaluation 24 Aug–1 Sep · Finale 4 Sep
**Judged on:** innovation, technical implementation, business relevance, scalability, impact.
**Builder:** Solo, 3–4 h/day ≈ 55–60 h total.

---

## 1. Why this wins (positioning)

Judges are Unilog tech leaders. Their reality (see `unilog-research.md`):

- Their moat is a 10M-SKU content library built by **human content teams** — expensive, slow.
- Their own AI product **HyperScale** (Oct 2025) only ships descriptions/blogs/synonyms. Item matching, grouping, image agents are "coming soon" — **we build their roadmap, plus the piece nobody ships: trust.**
- Their problem statement explicitly says: hallucinated industrial data causes dangerous/expensive order errors; solutions must assign confidence and verify against sources.

**Differentiator (locked decision):** Trust Engine (per-attribute confidence + provenance + cross-source conflict detection) as the spine, multi-agent live visualization as the presentation layer. Most entries will be "MPN → GPT → JSON." We show *why each field can be trusted*.

**Pitch math for the deck:** manual enrichment ≈ ₹150–250/SKU (human content teams) vs SKUForge ≈ ₹4–8/SKU, minutes not days. 85% of attributes auto-approved above confidence threshold; humans only review flagged 15%.

---

## 2. Locked decisions (from grilling)

| Decision | Choice |
|---|---|
| Input | MPN + brand + one-line description (official statement, verbatim) |
| Differentiator | (a) Trust Engine + (d) agent-theatre demo layer |
| LLM provider | OpenAI (paid keys) |
| Search | OpenAI Responses API built-in `web_search` (no Tavily) |
| Backend | Python + FastAPI, hand-rolled async agent orchestration (no LangChain) |
| Frontend | Next.js + Tailwind |
| Demo vertical | Electrical (Schneider/Eaton/Leviton/Hubbell MPNs) + 1 plumbing SKU as cross-vertical proof |
| Schema | Category-aware: classify → per-category attribute template (~10 templates, IDEA/UNSPSC-aligned), generic fallback |
| HITL | Review queue only (approve/edit/reject flagged attributes) |
| Scalability proof | Batch mode: CSV of 50–100 MPNs, throughput + cost/SKU dashboard |
| Evidence strategy | Live fetch + local cache layer; demo SKUs pre-warmed; video shows 1 cold SKU live |
| Deliverables | Demo video (3 min) + repo w/ architecture README + one-pager deck + live deploy (Vercel + Railway/Render) |
| Name | **SKUForge** |

---

## 3. Architecture

```
CSV / single input (MPN, brand, description)
        │
        ▼
┌─ Orchestrator (async Python, per-SKU state machine) ─────────────┐
│                                                                  │
│  1. SCOUT agent      → web_search: manufacturer page, datasheet  │
│                        PDFs, distributor listings (Grainger/     │
│                        Zoro/Platt). Ranks sources by trust tier. │
│  2. CLASSIFIER agent → UNSPSC-style category → load attribute    │
│                        template (10 curated electrical + generic)│
│  3. EXTRACTOR agent  → per-source structured extraction          │
│                        (Strict Structured Outputs). PDFs/images  │
│                        via multimodal input = VLM checkbox.      │
│  4. VALIDATOR agent  → cross-source merge: agreement scoring,    │
│                        unit normalization, CONFLICT detection,   │
│                        per-attribute confidence + provenance     │
│  5. COMPOSER agent   → SEO title, short/long description,        │
│                        search synonyms, cross-reference hints    │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
        │                                    │
        ▼                                    ▼
  Evidence cache (SQLite +           Product record store (SQLite)
  ./cache/ for HTML+PDFs,            status: auto-approved /
  keyed by URL hash)                 needs-review / rejected
        │
        ▼
  Next.js dashboard: record view · trust panel (evidence links,
  conflicts) · agent theatre (live SSE stream of agent steps) ·
  HITL review queue · batch dashboard (throughput, cost/SKU)
```

**Agent events stream to frontend via SSE** — the "agent theatre" is just the orchestrator emitting step events; near-zero extra backend cost, huge demo value.

### Trust Engine spec (the core IP)

Per attribute:
- `value`, `unit` (normalized), `sources: [{url, source_type, quote/page, fetched_at}]`
- `confidence` (0–1): computed from source count, source trust tier (manufacturer > distributor > marketplace), inter-source agreement, extraction certainty
- `status`: `verified` (≥2 agreeing sources) · `single-source` · `conflict` (sources disagree → shows both values + sources) · `generated` (LLM-inferred, lowest tier, always flagged)
- Threshold: confidence ≥ 0.8 auto-approve, else HITL queue

**Never silently pick a winner in conflicts.** Showing "datasheet says 2.5 kg, Zoro says 3.1 kg — flagged" IS the demo moment.

### Output record (Unilog's own commerce-ready checklist)

SEO title · short + long description · normalized attribute-value pairs (per category template) · taxonomy placement · datasheet/spec-sheet links · image URLs found · certifications (UL, CE…) · search synonyms · competitor/equivalent MPN hints (roadmap-lite: show if found, don't chase) · per-attribute trust metadata · export as JSON + CSV ("syndication-ready").

---

## 4. Model routing (OpenAI)

| Stage | Model | reasoning_effort |
|---|---|---|
| Orchestration / routing | gpt-5-mini | low |
| Source relevance filtering | gpt-5-nano | minimal |
| Extraction (HTML/PDF/image) | gpt-5-mini + Structured Outputs | low |
| Classification → template | gpt-5-mini | low |
| **Validation / conflict adjudication / confidence** | **gpt-5.1** | **medium** |
| Commerce copy (title, desc, SEO) | gpt-5.1 | low |
| Batch mode default | gpt-5-mini end-to-end | minimal/low |

Set a **hard per-day spend cap** on the OpenAI key before deploying.

**Claude Code usage:** Sonnet for building (`/model`), Opus/Fable only for architecture or nasty bugs. `/clear` between unrelated tasks.

---

## 5. Timeline (17 days)

| Dates | Milestone | Done when |
|---|---|---|
| **Aug 5–7** | Skeleton | One hardcoded SKU runs end-to-end (search → extract → validate → record) in terminal. Ugly is fine. |
| **Aug 8–11** | Trust Engine | Confidence scoring, conflict detection, provenance, unit normalization. 10 category templates. |
| **Aug 12–14** | Frontend | Record view, trust panel, agent theatre (SSE), HITL queue. |
| **Aug 15–16** | Batch + cache | 50–100 MPN CSV run, cost/throughput dashboard, cache hardening. |
| **Aug 17–18** | Deploy + harden | Vercel + Railway/Render, spend caps, plumbing SKU cross-vertical test. |
| **Aug 19–21** | Demo assets | Video scripted + recorded, README architecture diagram, one-pager deck. |
| **Aug 22** | **Submit** | Buffer day. Never submit on deadline day. |

Rule: if a milestone slips 2+ days, cut scope from *later* milestones (batch shrinks to 25 SKUs, deploy becomes optional) — never cut the Trust Engine or the video.

---

## 6. Demo video script (3 min)

1. **0:00–0:20 Hook:** "Distributors receive this —" (show 3-column CSV: MPN, brand, one-liner) "— and need this." (show full commerce record). "Human teams take days per catalog. SKUForge does it in minutes — and tells you exactly what to trust."
2. **0:20–1:20 Single SKU live:** type Schneider breaker MPN → agent theatre streams (Scout finds datasheet PDF + Grainger listing → Extractor → Validator) → record appears with confidence badges.
3. **1:20–2:00 Trust moment:** click attribute → evidence quote + source link. Show a **conflict**: two sources disagree on one spec, flagged, human resolves in HITL queue in 5 seconds. "Hallucinated industrial data causes wrong orders. SKUForge never guesses silently."
4. **2:00–2:35 Scale:** batch dashboard, 50 SKUs, cost/SKU counter, 85% auto-approved. One plumbing SKU shown: "same pipeline, any vertical."
5. **2:35–3:00 Business close:** cost math vs manual enrichment, architecture slide 3 s, "built for the 10-million-SKU world."

---

## 7. Risks

| Risk | Mitigation |
|---|---|
| Distributor sites block scraping | Cache layer (decision b); prefer manufacturer PDFs (rarely blocked); pre-warm all demo SKUs |
| OpenAI cost blowout | Spend cap, nano/mini for volume, cache eliminates re-fetch |
| Solo scope creep | Locked decisions above are the contract; everything else = "roadmap" slide |
| Live deploy dies during evaluation | Video never depends on live link; deployed app seeded with cached demo SKUs |
| gpt-5 model names/API drift | Verify current model IDs + Responses API web_search on day 1 (Aug 5) before building around them |

---

## 8. Submission checklist

- [ ] 3-min demo video (script above, recorded from local run)
- [ ] Repo: clean structure, README with architecture diagram + "defend the architecture" section (why hand-rolled agents, why cache, why confidence model)
- [ ] One-pager deck: problem → gap in HyperScale/Akeneo/Salsify → architecture → cost math → roadmap (knowledge graph of equivalents, feedback learning, image agents)
- [ ] Live link (Vercel + Railway/Render) with seeded demo SKUs
- [ ] Submitted via portal by **22 Aug**

---

## 9. Reference

- Research report: `unilog-research.md` (copy into this folder) — Unilog pain points w/ quotes+URLs, commerce-record checklist, HyperScale gap analysis, IDEA/UNSPSC schema notes.
- Demo SKU shortlist to build during skeleton phase: 3× Schneider, 2× Eaton, 2× Leviton, 1× Hubbell, 1× Siemens breaker/contactor/switch + 1 plumbing (e.g., a Moen/Delta valve).
