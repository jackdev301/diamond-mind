# Handoff: Form Speed, BABIP, and Lineup Quality Fields

**From:** Track A (Arnav)
**To:** Track B (Jack)
**Date:** 2026-05-16

## What landed

New nullable/optional contract fields for betting-analysis signals.

### `PitcherFormWindow`

- `babip: Optional[float]`

Computed in `build_starter_form_window()` as:

```text
(hits_allowed - home_runs_allowed)
/ (batters_faced - strikeouts - walks - home_runs_allowed)
```

Returns `None` if the denominator is unavailable or zero.

### `TeamFormWindow`

- `stolen_bases: int`
- `caught_stealing: int`
- `stolen_base_attempts: int`
- `stolen_base_success_rate: Optional[float]`
- `lineup_quality_score: Optional[float]`

`lineup_quality_score` is the average estimated wOBA of the top six team hitters by plate appearances inside the form window.

## Raw ingestion/schema changes

- `player_game_logs.caught_stealing` added and parsed from MLB boxscore `caughtStealing`.
- `team_form_windows` cache rows store the new speed/lineup fields.
- `pitcher_form_windows` cache rows store `babip`.
- Existing SQLite DBs are upgraded via additive compatibility ALTERs in `app/database.py`.

## Verification

- `pytest`: green
- `frontend lint/build`: green

