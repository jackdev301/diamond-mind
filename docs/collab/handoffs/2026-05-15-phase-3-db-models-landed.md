# 2026-05-15 — Phase 3 DB models landed

**From:** Track A (Arnav)
**To:** Track B (Jack)
**Status:** informational — no action required from you

## What's available now

- 17 ORM tables under `app/models/*`, registered on `Base.metadata`.
- `scripts/init_db.py` creates them all (idempotent; `--drop` for a clean rebuild).
- `tests/test_models.py` exercises a round-trip on every table; 8/8 pytest green.

Tables (by file):

| File | Tables |
|------|--------|
| `app/models/entities.py` | `teams`, `players` |
| `app/models/games.py` | `games`, `team_game_logs`, `player_game_logs`, `pitcher_game_logs` |
| `app/models/players.py` | `team_form_windows`, `player_form_windows`, `pitcher_form_windows`, `reliever_form_windows` |
| `app/models/bullpen.py` | `reliever_usage`, `bullpen_fatigue` |
| `app/models/odds.py` | `odds_snapshots`, `weather_snapshots` |
| `app/models/reports.py` | `model_runs`, `bet_evaluations`, `obsidian_exports` |

## What this means for your track

**Do NOT import from `app.models`.** That's intentionally Track A territory. Your code should import the dataclasses from `app.contracts` — those are the shapes that flow between tracks. I'll write query helpers in Phase 5 that load DB rows and hydrate the dataclasses for you.

You *can* peek at the model files to understand which columns will be available, e.g. when designing what `BetEvaluation` should record — but please don't write to `bet_evaluations` directly. The plan is:

1. Track B produces `BetEvaluation` dataclass instances.
2. Track A persists them via a writer helper (lands in Phase 9-ish).
3. The DB ORM row (`BetEvaluationRow`) has extra fields for postgame grading that Track B doesn't need to know about.

## Reliever form: two tables not one

Spec mentioned `pitcher_form_windows`. I split it into `pitcher_form_windows` (starters) and `reliever_form_windows` because their fields differ (starts vs appearances, inherited-runner %). Matches the dataclass split in `app.contracts` (`PitcherFormWindow` vs `RelieverFormWindow`). If you'd prefer a single table, raise it via PR — but I think this is cleaner.

## What you can start on right now

You're unblocked for Phase 4 (betting utilities — pure math, no DB) and Phase 6 (bullpen scoring — takes `BullpenState` dataclass, returns scores). Fixtures aren't written yet; build against hand-constructed dataclass instances in your tests for now. I'll commit fixture JSON files alongside Phase 5 (recent form engine), probably tomorrow.

## What's NOT done

- No real data in the DB yet (Phase 7 ingestion).
- No query helpers (Phase 5).
- No fixture files (coming with Phase 5).
- No alembic / migrations — `create_all()` is fine for MVP. If we change a schema, drop and re-init.

## Open question for you

`BetEvaluationRow.supporting_factors` and `opposing_factors` are stored as JSON strings (TEXT column). The dataclass has them as `List[str]`. When you build the report generator and we wire persistence, do you want a helper to handle serialization, or would you rather work with raw strings and let Track A serialize at the persistence boundary? Leaning toward the latter — Track B stays pure, no JSON juggling in your code. Reply via a new handoff if you disagree.
