# Handoff: Phase 11 — Pregame Update & Backfill Scripts

**From:** Track A (Arnav)
**To:** Track B (Jack)
**Date:** 2026-05-15

## What landed

### `build_bullpen_state()` in `app/features/recent_form.py`

The function you need to build `BullpenState` from the database. Key points:

```python
from app.features.recent_form import build_bullpen_state
from app.contracts import BullpenState

state: BullpenState = build_bullpen_state(
    session, team_id=143, as_of_date=date(2026, 5, 15)
)
```

**Confirmed as per your spec:**
- `back_to_back_relievers` → `List[int]` pitcher_ids (pitched yesterday AND day before)
- `three_in_four_relievers` → `List[int]` pitcher_ids (3+ appearances in last 4 days)
- `recent_usage` → last 5 days of `RelieverUsage` records, newest first
- `relievers` → `List[RelieverFormWindow]` for each reliever who appeared (L20 window)

Returns `None` if the team doesn't exist in the DB.

### `scripts/run_pregame_update.py`

Daily orchestration. Run it once before first pitch:

```bash
python scripts/run_pregame_update.py --date 2026-05-15
python scripts/run_pregame_update.py  # uses today's date
python scripts/run_pregame_update.py --dry-run  # schedule fetch only, no DB writes
```

Sequence:
1. Fetch today's schedule → Game rows + probable starter IDs
2. Ingest yesterday's completed box scores → TeamGameLog / PlayerGameLog / PitcherGameLog
3. Recompute team form windows (Season/L20/L10/L5)
4. Recompute hitter form windows
5. Recompute starter form windows
6. Build BullpenState snapshots for all teams
7. Commit

### `scripts/backfill_history.py`

Seeds historical data:

```bash
python scripts/backfill_history.py --days 30
python scripts/backfill_history.py --start 2026-04-01 --end 2026-05-14
python scripts/backfill_history.py --start 2026-04-01 --recompute-form
```

## What this means for Track B

Once `run_pregame_update.py` runs daily, you can replace any fixture-based
`BullpenState` with a real DB load:

```python
# Before (fixture):
from tests.fixtures import load_fixture
state = load_fixture("bullpen_state_phi_2026-05-15", BullpenState)

# After (real):
from app.features.recent_form import build_bullpen_state
state = build_bullpen_state(session, team_id=143, as_of_date=date.today())
```

The `score_bullpen(state)` call and everything downstream is unchanged.

## Phase 12 readiness

I can build the Anthropic client wrapper (`app/llm/anthropic_client.py`) for
Phase 12. Tell me the call shape you want — e.g.:

```python
polish_report(report_markdown: str, context: dict) -> str
```

or something more structured. I'll wire up the key management and stub it
cleanly so it's testable without a real API key.
