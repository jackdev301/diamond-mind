# Track A — Data Platform

**Owner:** Arnav (+ Claude)
**Mission:** Build the structured-data foundation. Ingest MLB data, store it, compute recent-form features. Produce the dataclass instances Track B consumes.

## Scope

- Phase 2 — Project skeleton, config, .env, test setup
- Phase 3 — Database models and initialization
- Phase 5 — Recent form calculation engine (Season / L20 / L10 / L5; starters L10/L5; relievers L20/L10/L5)
- Phase 7 — MLB Stats API ingestion (schedule, teams, players, games, box scores, pitcher usage)
- Phase 11 (partial) — `init_db.py`, `run_pregame_update.py`, `backfill_history.py`

## Deliverables

1. SQLite database populated from MLB Stats API.
2. Documented table schemas in `interfaces/db-schema.md`.
3. **The dataclass shapes in `interfaces/data-contracts.md`** — agreed jointly with Track B before either side writes much code. Track A produces these; Track B consumes them.
4. Query helpers that return those dataclasses (e.g. `load_team_form(team_id) -> TeamFormWindow`).
5. Tests for recent-form math and ingestion parsers.

## Status

- [x] Phase 2 — skeleton
- [x] Data contracts drafted in `interfaces/data-contracts.md` (strawman; Jack to review)
- [x] Phase 3 — DB models (`app/models/*`, `scripts/init_db.py`, 17 tables, tests green)
- [x] Phase 5 — recent form engine (`app/features/recent_form.py`, fixtures, loaders for Track B)
- [ ] Phase 7 — MLB Stats API ingestion ← next
- [ ] Phase 11 — CLI scripts (data side)

## Working order (so Jack is never blocked)

1. **Day 1 joint:** agree the dataclass shapes in `interfaces/data-contracts.md`. Ship example/fixture JSON for each.
2. From there, Track A and Track B work in parallel against the same fixtures.
3. Integration handoff once Track A query helpers return real data — Jack swaps fixtures for real loads.
