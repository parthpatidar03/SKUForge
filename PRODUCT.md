# SKUForge

## Register

product

## Product purpose

Turns minimal supplier input (a manufacturer part number, a brand, one line of
text) into a commerce ready product record where every attribute carries a
confidence score, a cited source, and the exact sentence supporting it.
Cross source disagreements are surfaced, never silently resolved.

The product is not the extraction. The product is the **trust layer**: proof
that a generated specification can be published without a human re reading the
whole datasheet.

## Users

**Primary: catalog content reviewer at a B2B distributor.**
Sits in a content operations team. Today they read manufacturer PDFs and type
specifications into a PIM by hand. Their work is measured in SKUs cleared per
day. They are not engineers. They care about one question per value: can I
trust this enough to publish it, and if not, what do I check.

They work a **queue**, not a canvas. The interface is scanned, filtered and
cleared, repeatedly, for hours.

**Secondary: catalog or eCommerce manager.**
Cares about throughput and risk. Wants to know how many SKUs are done, how many
need attention, and what it costs.

**Tertiary, short term: hackathon judges.**
Evaluating on innovation, technical implementation, business relevance,
scalability, impact. They will open the deployed link once, for a few minutes,
and need to understand the trust story without a guide.

## Scene

A content reviewer at a desk in a lit office, mid morning, working through a
list of flagged attributes on a laptop. Sometimes a manager checks progress on a
phone between meetings.

Daylight, sustained reading of dense factual text, long sessions. This forces a
**light interface**. A dark dashboard here would be a category reflex borrowed
from developer tooling, not a response to how the work actually happens.

## Tone

Factual, calm, precise. The interface should feel like a well made instrument
for checking things: closer to a laboratory record or an audit report than to a
consumer SaaS dashboard.

Never celebratory. No emoji. No exclamation. Confidence is expressed through
clarity and restraint, because the entire product claim is trustworthiness.

## Strategic principles

1. **Evidence is the interface.** The quote and the source link are primary
   content, not a detail view. If a number is on screen, its proof should be
   one glance or one click away.
2. **State must be readable at a distance.** verified, single source, conflict,
   human reviewed. A reviewer should sort the queue with their eyes before
   reading a single word.
3. **Never imply certainty the system does not have.** No rounding a 0.75 up to
   "good". Uncertainty is shown plainly.
4. **The queue is the job.** Optimise for clearing many attributes quickly, not
   for admiring one record.
5. **Explain the mechanism.** The five agent pipeline is visible while it runs,
   because a reviewer who understands where a value came from trusts it more.

## Anti references

- Dark, neon accented "AI product" dashboards. This is the reflex look for
  anything with a model behind it, and the current UI has fallen into it.
- Gradient hero panels, glowing borders, glass cards.
- Big number hero metrics with a small label underneath.
- Consumer analytics dashboards with rounded pastel cards and playful copy.
- Anything that reads as a template with this product's words pasted in.

## Constraints

- Next.js + React + Tailwind, single page dashboard.
- Must work at mobile, tablet and laptop widths. Reviewers use laptops,
  managers check on phones.
- No external font or asset CDN dependency at runtime where avoidable.
- The backend and API contract are fixed and working. This is a presentation
  layer refinement, not a rebuild.
