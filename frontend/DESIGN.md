# Diamond Mind — Design System (source of truth)

One-line aesthetic direction: **a refined "quant terminal" stadium scoreboard —
dark instrument panel, box-score grids, stencil display numerals, with a
restrained grass-green / clay-amber field accent on the existing GitHub-dark base.**

This is an *extension* of an already-shipped house style, not a redesign. The
anti-slop mandate here means: do not regress the existing terminal aesthetic
into a generic SaaS dashboard. No indigo/violet hero, no glassmorphism, no
emoji icons, no uniform `rounded-2xl`, no centered hero + 3 equal cards.

## 1. Palette (constrained, one confident accent system)

Inherited base (unchanged — do not touch):
- `--bg #080C10` · `--surface #0D1117` · `--surface-2 #161B22` · `--surface-3 #1C2330`
- `--border #1C2330` · `--border-2 #2D3748`
- text ramp: `--text #CDD9E5` → `--text-2 #768390` → `--text-3 #444C56`
- signal: `--blue #58A6FF` (market/flat), `--green #3FB950` (edge/Kelly),
  `--amber #D29922` (caution), `--red #F85149` (negative), `--purple #BC8CFF`

New baseball field accent (the one deliberate addition — earthy, not neon):
- `--grass #1A6B2A` — deep outfield green (structural accent: dividers, pills)
- `--clay #B5651D` — infield clay amber (the single hero accent on Track Record)
- `--grass-dim #0D3315` / `--clay-dim #3D1F08` — pill fills only

Rule: green/blue/red keep their existing *quant* meaning (edge, market, loss).
grass/clay are *identity* colors — used for chrome (dividers, watermark,
section accents, the Track Record P&L hero), never to encode a stat value.

## 2. Type scale (deliberate, not one-font-no-scale)

Two families, already loaded:
- `--font-mono` JetBrains Mono — all data, labels, tabular values (the voice
  of the product).
- `--font-display` Syne 700/800 — headlines and the new `--font-scoreboard`
  alias for big stencil numerals.

Display numeral treatment (new `.scoreboard-num`): Syne 800, `tabular-nums`,
`letter-spacing: -0.04em`. Used ONLY for headline figures (Brier, P&L total,
confidence %, Kelly %) so a number reads like a stadium scoreboard, not body
text. Everything else stays mono.

Step scale in use: 28/22/20 (page titles) · 15/13 (body+data) · 11/10/9
(labels, uppercase, `0.04–0.1em` tracking). No new arbitrary sizes.

## 3. Spacing & rhythm

Inherited 4px-ish rhythm kept: card padding 14–20px, section gaps 24px,
data-row padding 5–6px. New `.box-score-grid` enforces a real tabular rhythm
(6px 10px cells, ruled columns) so charts/tables read like an actual box score
rather than floating divs. `.infield-divider` replaces ad-hoc
`borderLeft: 2px solid` tier accents with a bottom rule + a 32px clay tab —
a deliberate, repeatable motif.

## 4. Baseball identity layer (refined, not kitsch)

- `.diamond-watermark` — a single 200×200 SVG diamond wireframe (the infield),
  `opacity 0.03`, fixed bottom-right, `aria-hidden`, `pointer-events:none`,
  `z-index:0`. Decorative texture only; never competes with data.
- `.box-score-grid` — ruled grid header on `--surface-2`, the canonical layout
  for any tabular metric block.
- `.stat-pill-grass` / `.stat-pill-clay` — small uppercase status pills
  (10px/700/0.06em) for "ACCRUING", tier tags, etc.
- Scoreboard numerals for hero figures (see §2).
- No clip-art, no baseball emoji, no green felt gradients.

## 5. Motion (has a reason)

Reuse existing `fade-up` (entrance) and `fillBar` (value reveal). SVG charts
animate stroke/area in with a single `chartDraw` keyframe (250–600ms,
`cubic-bezier(0.16,1,0.3,1)`) — motion communicates "data populating", matching
the existing `duelGrow`. Respect `prefers-reduced-motion` (charts render at
final state, no animation).

## 6. Charts (hand-rolled SVG, zero new deps)

All five Track Record charts are inline `<svg viewBox>` with `role="img"` and
a descriptive `aria-label`. No recharts/d3/chart.js/etc. — that would be slop
*and* a dependency violation. Axes/ticks in mono 9px `--text-3`. Lines use the
quant palette (blue=flat, green=Kelly). Every chart has an explicit, designed
`.accruing-state` empty state — never a blank div, never a fabricated number
(hard project rule: no fake data).

## 7. Progressive disclosure

`ExplainTooltip` — inline `ⓘ` affordance, keyboard-focusable, click-outside
close, popover from `--surface-2`. Copy is the canonical `GLOSSARY` map (12
terms, exact spec copy, zero forbidden betting words). `GlossaryPanel` —
right drawer opened by a persistent `?` button at the right end of the nav,
sectioned (Quant Terms / Recommendation Tiers / Model Components).

## 8. Anti-slop self-audit (checked before done)

- [x] No indigo/violet/purple gradient hero — base is GitHub-dark; accent is earthy grass/clay
- [x] No glassmorphism — surfaces are flat panels with 1px rules
- [x] Not uniformly over-rounded — radii stay 3–6px as in the existing system
- [x] No emoji as icons or in headings — `ⓘ`/`?` glyphs and SVG only
- [x] Not centered-hero + 3 equal cards — box-score grids, asymmetric strips
- [x] Tailwind defaults unused — bespoke tokens, mono type, custom shadows
- [x] Real type scale + one confident accent (clay) + intentional rhythm
- [x] Charts are hand-rolled, every one has a designed empty state
</content>
</invoke>
