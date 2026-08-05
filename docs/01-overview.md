# SKUForge — What This Is (Simple English)

*Living document. Updated as the project grows. Source material for the final LinkedIn post.*

## The problem we solve

Industrial distributors (companies selling breakers, valves, motors to contractors) receive product lists from suppliers that contain almost nothing: a part number, a brand name, one line of text. Example:

> `HOM230CP, Square D, "30A 2 pole breaker"`

To sell that part online they need a full product page: title, descriptions, 10+ technical specs, category, certifications, images, search keywords. Today humans build those records by hand — companies like Unilog employ whole content teams for it. It's slow (days per catalog), expensive (₹150-250 per product), and doesn't scale to 100,000-product catalogs.

The obvious "fix" — ask ChatGPT to fill in the specs — is dangerous. LLMs hallucinate. A hallucinated voltage rating on an industrial part causes wrong orders, returns, even safety issues.

## What SKUForge does

You type the part number, brand, and one-line description. Five AI agents work in sequence, live on screen:

1. **Scout** — searches the web for evidence: the manufacturer's official page, PDF datasheets, distributor listings (Grainger, Zoro…).
2. **Classifier** — figures out what kind of product it is and loads that category's spec checklist (a breaker needs voltage/amps/poles; a valve needs pressure/connection size).
3. **Extractor** — reads each source (including PDFs, using vision) and pulls out spec values, keeping the exact quote it found each value in.
4. **Validator** — the heart of the system. Compares values across sources. Every spec gets a confidence score and a status: **verified** (2+ sources agree), **single-source**, or **conflict** (sources disagree — both values shown, a human decides). It never silently guesses.
5. **Composer** — writes the sales copy (SEO title, descriptions, search keywords) using ONLY verified facts.

Anything uncertain lands in a human review queue where one click resolves it. Everything confident is auto-approved. Result: a commerce-ready product record in ~a minute for pennies, with a paper trail for every single value.

## Why this is different from "just use AI"

Every value in the output answers three questions: **what is it, where did it come from, how sure are we.** That trust layer — confidence scores, clickable source quotes, explicit conflict flagging — is what makes AI enrichment safe enough for industrial commerce, and it's the thing existing tools (including Unilog's own HyperScale, Akeneo AI, Salsify) don't do today.

## Technologies used

- **Python + FastAPI** — backend and agent orchestration (hand-written async loop, no agent framework — easier to debug and defend)
- **Two interchangeable AI providers** — the system needs exactly three model capabilities (web search with citations, PDF/image reading, and guaranteed-shape JSON output), and both **OpenAI's GPT-5 family** and **Google's Gemini** provide all three. One environment variable switches between them; no other code changes. Gemini's free tier means the whole system can run at zero cost.
- **Model routing** — cheap small models for the high-volume steps, the strongest model only for validation and final copy → cost stays at pennies per product (or nothing at all on the free tier)
- **Server-Sent Events (SSE)** — streams each agent's actions to the browser in real time (the "agent theatre")
- **SQLite + disk cache** — product records + every fetched page/PDF cached so nothing is downloaded twice
- **Next.js + Tailwind CSS** — dashboard: live pipeline view, confidence bars, evidence panels, review queue, batch stats
- **Mock mode** — full pipeline runs offline against recorded fixtures; used for tests and demo reliability

## Where it stands (live, on real websites)

Enriching a real Square D breaker from just `HOM230CP / Square D / "30A 2 pole
breaker"` takes about **87 seconds and 2 rupees**, and produces 12–13
specifications, each traced to the exact sentence in a manufacturer or
distributor spec sheet. Manual enrichment of the same record costs a content
team ₹150–250 and takes far longer.

Real-world lessons already baked in: manufacturer websites block bots (their
spec-sheet PDFs don't, so the system prefers those), and different sources often
state the same fact at different levels of detail — which the system now
recognizes as agreement rather than crying "conflict". What it *does* flag are
genuine disagreements, like two different barcodes or a net weight of 0.65 lb
against a shipping weight of 1 lb. Those go to a human; everything else
auto-approves.

## Built for

UniHack 2026 (Unilog AI Hackathon) — solo, ~3-4 hours/day. Challenge: "turn minimal product information into rich, structured, commerce-ready product intelligence."
