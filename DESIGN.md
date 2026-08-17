# SKUForge design system

Instrument, not dashboard. The reference points are an audit record and a lab
notebook: hairline rules, dense factual type, colour reserved for state.

## Color strategy

**Restrained.** Tinted neutrals carry the surface. One ink blue accent, kept
under roughly 10% of any view, used only for primary action, current selection
and links. Semantic state colour is separate from the accent and is the only
other colour permitted.

All values OKLCH. Every neutral is tinted toward the accent hue (250) so nothing
is a pure grey, and neither `#000` nor `#fff` appears anywhere.

### Neutrals

| Token | OKLCH | Role |
|---|---|---|
| `--paper` | `oklch(99% 0.003 250)` | Page ground, near white with a cool tint |
| `--surface` | `oklch(100% 0 0 / 0)` → white cards sit on paper via `--card` | |
| `--card` | `oklch(100% 0.002 250)` | Raised content: table, panels |
| `--sunken` | `oklch(97.2% 0.005 250)` | Toolbar, table header, code, evidence blocks |
| `--line` | `oklch(91% 0.008 250)` | Hairline borders, 1px only |
| `--line-strong` | `oklch(84% 0.012 250)` | Table rules, dividers needing weight |
| `--ink` | `oklch(24% 0.02 260)` | Primary text, warm near black |
| `--ink-2` | `oklch(45% 0.015 258)` | Secondary text, labels |
| `--ink-3` | `oklch(60% 0.012 256)` | Tertiary, captions, placeholder |

### Accent

| Token | OKLCH | Role |
|---|---|---|
| `--accent` | `oklch(48% 0.14 255)` | Primary button, links, focus ring |
| `--accent-hover` | `oklch(43% 0.15 255)` | Hover on primary |
| `--accent-weak` | `oklch(95% 0.03 255)` | Selected row, subtle fill |

### State

Muted, never neon. Chroma stays low so a full table of badges does not vibrate.

| State | Text | Fill | Meaning |
|---|---|---|---|
| verified | `oklch(43% 0.11 155)` | `oklch(96% 0.03 155)` | 2+ sources agree |
| single-source | `oklch(48% 0.10 75)` | `oklch(96.5% 0.035 75)` | capped, needs a human |
| conflict | `oklch(48% 0.15 25)` | `oklch(96% 0.035 25)` | sources disagree |
| generated | `--ink-3` | `--sunken` | no supporting source |
| human-reviewed | `oklch(43% 0.11 155)` | `oklch(96% 0.03 155)` | a person signed off |

Confidence bars use the same three hues, at full token chroma, on a `--line`
track. The bar is the only place colour may run edge to edge.

## Typography

One family. System stack, no webfont, no CDN dependency:
`-apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif`.
Monospace for identifiers, values and quotes:
`ui-monospace, "SF Mono", "Cascadia Code", Consolas, monospace`.

Attribute names, MPNs, numbers and evidence quotes are set in mono. That is the
instrument voice, and it separates machine-extracted fact from interface chrome
without adding colour.

Fixed rem scale, ratio ~1.2.

| Step | Size | Use |
|---|---|---|
| `--t-xs` | 0.6875rem | Badges, table captions, meta |
| `--t-sm` | 0.8125rem | Labels, secondary text |
| `--t-base` | 0.875rem | Body, table cells, controls |
| `--t-md` | 1rem | Panel headings |
| `--t-lg` | 1.25rem | Record title |
| `--t-xl` | 1.5rem | Page title, wordmark |

Numerals: `font-variant-numeric: tabular-nums` on every figure that sits in a
column. Uppercase labels get `0.06em` tracking, never elsewhere.

## Space and layout

4px base. Steps: 4, 8, 12, 16, 24, 32, 48.

Rhythm is deliberately uneven: 24px between major regions, 12px inside a panel,
8px between a label and its value. Uniform padding everywhere is the monotony
this design is trying to avoid.

Structure: fixed top bar, single content column at `max-width: 1200px`, footer.
No sidebar. The work is a queue, and the queue is the page.

Responsive is structural, never fluid type:

| Width | Behaviour |
|---|---|
| `< 640px` | Table becomes a stacked list. Controls go full width. Record view single column. |
| `640 to 1024px` | Table returns, condensed. Record view single column, panels side by side. |
| `> 1024px` | Full table. Record view splits: attributes left, copy and sources right. |

## Elevation

None. No box shadows, no glass, no blur. Separation is achieved with 1px
`--line` borders and the `--sunken` fill. A single exception: the toast, which
is genuinely floating and takes a soft shadow to prove it.

## Components

Every interactive element ships default, hover, focus-visible, active, disabled,
and where relevant loading and error. Focus is a 2px `--accent` ring at 2px
offset, never removed.

- **Button.** 6px radius, 36px min height. Primary: accent fill, paper text.
  Secondary: card fill, `--line` border. Ghost: text only.
- **Input.** 6px radius, `--line` border, `--card` fill, accent ring on focus.
- **Badge.** 999px radius, state fill, state text, 1px state border at 30%.
- **Panel.** `--card` fill, 1px `--line`, 8px radius, sunken header strip.
- **Table.** Sunken header, hairline row rules, `--accent-weak` on hover.
- **Skeleton.** Sunken blocks that match final content geometry. Never a
  centred spinner in a content region.

## Motion

180ms, `cubic-bezier(0.22, 1, 0.36, 1)` (ease-out-quart). Colour, opacity and
transform only. Confidence bars animate width once on mount, 500ms, because
that reads as the value settling rather than decoration. Everything respects
`prefers-reduced-motion`.

## Brand mark

A 4 by 4 dot grid with the diagonal filled: extraction resolving into a
verified value. Drawn inline as SVG, reused for the favicon at 32 and 16px, so
there is no external asset request and no separate file to drift.

## Bans, specific to this product

- No dark ground. This surface is read in daylight for hours.
- No accent colour used decoratively. If it is not action, selection or link,
  it is a neutral.
- No rounding a confidence figure to make it look better.
- No emoji, no exclamation marks, no celebratory copy.
- No side-stripe borders, gradient text, glass, or hero metric blocks.
