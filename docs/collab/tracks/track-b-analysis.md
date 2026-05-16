# Track B — Analysis & Output

**Owner:** Jack (+ his agent)
**Mission:** Turn structured data into intelligence. Betting math, bullpen scoring, daily report generation, Obsidian export. Consumes the dataclasses Track A produces.

## Scope

- Phase 4 — Betting utilities (American odds → implied probability, edge, recommendation tiers)
- Phase 6 — Bullpen intelligence (fatigue, overall quality, available quality, vulnerability, explanation builder)
- Phase 8 — Odds / weather client structure (fail gracefully when API keys missing)
- Phase 9 — Daily report generator (deterministic / template-based markdown first)
- Phase 10 — Obsidian export (vault writer, wiki links, file path conventions)
- Phase 11 (partial) — `run_daily_report.py`, `run_postgame_update.py`

## Deliverables

1. Pure betting math functions with tests.
2. Bullpen scoring functions (fatigue, quality, available quality, vulnerability) with tests — take a `BullpenState` dataclass as input, return scores + labels.
3. Odds/weather clients with stubbed behavior when keys missing.
4. Daily report generator that takes Track A's dataclasses and emits markdown.
5. Obsidian vault writer following the path conventions in spec.
6. Tests for everything pure.

## Status

- [x] Data contracts drafted in `interfaces/data-contracts.md` (Arnav shipped strawman v0.1; accepted as-is)
- [ ] Phase 4 — betting utilities
- [x] Phase 6 — bullpen intelligence (`app/features/bullpen_fatigue.py`, `bullpen_quality.py`, `bullpen_vulnerability.py`)
- [ ] Phase 8 — odds/weather clients
- [ ] Phase 9 — daily report generator
- [ ] Phase 10 — Obsidian export
- [ ] Phase 11 — CLI scripts (analysis side)

## Working agreements specific to Track B

- **Pure functions where possible.** Bullpen and betting scoring should be `(dataclass) -> result`. No I/O inside the math.
- **No invented data.** If you need a stat that's not in the agreed dataclass, raise it in a handoff before adding a fallback default. Don't silently fabricate.
- **Report templates are markdown.** Keep them inspectable; the LLM polish layer (Phase 12) comes later.
- **Wiki-link conventions** for Obsidian go in `interfaces/obsidian-paths.md` once you start Phase 10 — document filename patterns so we don't end up with two conventions.

## Currently blocked on

- Nothing. Phase 5 fixtures from Arnav will enable fixture-based tests, but Phase 4 and 9 can proceed without them.

## Notes for Jack's agent

- Read `docs/collab/README.md` first.
- Re-read `interfaces/data-contracts.md` at the start of every session — it's the source of truth for shapes.
- Don't reach into `app/ingestion/` or `app/models/` — that's Track A territory. If you need something from there, request via a handoff.
- This is a betting **verification** system, not a pick bot. The language rules in the project spec (no "lock", "guaranteed", "hammer" — use "Strong Lean / Lean / Pass / Avoid / Need More Info") apply to every report string you generate.
