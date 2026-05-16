# 2026-05-15 — Phase 5 recent form engine + fixtures landed

**From:** Track A (Arnav)
**To:** Track B (Jack)
**Status:** unblocks Track B for testing — please pick up the fixture files

## What's available

### `app/features/recent_form.py`
Pure helpers (Track B can call these freely):

- `classify_trend(window_metric, season_metric, sample_size, min_sample, higher_is_better, strong_threshold)` → `TrendLabel`. The single source of truth for trend labels. Higher-is-better=False inverts for ERA/WHIP.
- `aggregate_hitter(...)`, `aggregate_pitcher(...)`, `aggregate_team(...)` — take raw counters, return rate-stat dicts. Useful if you want to do scenario math.
- `weighted_form_metric(metrics_by_window, weights=None)` — combines per-window estimates using the 50/25/15/10 weights from PROJECT_BRIEF.md. Missing windows have their weight redistributed proportionally. **This is the helper I'd reach for when building the model probability inputs for `BetEvaluation`.**

DB-backed (you don't need these directly):

- `build_team_form_window`, `build_hitter_form_window`, `build_starter_form_window`, `build_reliever_form_window` — compute from `*_game_logs`.
- `upsert_*_form_window`, `load_team_form_window`, `load_hitter_form_window` — persistence. More loaders coming as Phase 7 ingestion lands real data.

### `tests/fixtures/` — the things you'll actually use

All 7 contract shapes have a fixture file:

| File | Loads as |
|------|----------|
| `team_form_phi_l10.json` | `TeamFormWindow` |
| `team_form_phi_season.json` | `TeamFormWindow` |
| `pitcher_form_wheeler_season.json` | `PitcherFormWindow` |
| `reliever_form_alvarado_l20.json` | `RelieverFormWindow` |
| `bullpen_state_phi_2026-05-15.json` | `BullpenState` (with nested relievers + recent_usage) |
| `game_context_phi_vs_nym_2026-05-15.json` | `GameContext` |
| `odds_snapshot_phi_vs_nym.json` | `OddsSnapshot` |
| `weather_snapshot_phi_vs_nym.json` | `WeatherSnapshot` |

Load them via:

```python
from tests.fixtures import load_fixture
from app.contracts import BullpenState

state = load_fixture("bullpen_state_phi_2026-05-15", BullpenState)
```

The loader handles `date`/`datetime` parsing and the `WindowKey`/`TrendLabel` enums. Nested `RelieverFormWindow` / `RelieverUsage` inside `BullpenState` are hydrated too.

## Where this leaves Phase 6 (your bullpen scoring)

The `bullpen_state_phi_2026-05-15` fixture is deliberately interesting:

- 4 IP yesterday, 62 pitches, 4 relievers used → moderate fatigue per the formula.
- Closer pitched yesterday → +10.
- Alvarado pitched both of the last 2 days → +8 (back-to-back).
- High-leverage Alvarado pitched yesterday → +8.
- Relievers' season form is generally strong (ERAs ~2.30–3.12, K/9 ~10–12.5) → overall_bullpen_quality should be high.
- Alvarado should likely be flagged "limited" (back-to-back + closer-like usage); Kerkering pitched yesterday so also "limited"; Strahm is fresh and elite.

When you implement the vulnerability formula from PROJECT_BRIEF.md:
```
Bullpen Vulnerability = 0.55 * Fatigue + 0.45 * (100 - Available Bullpen Quality)
```
… this fixture should produce a moderate vulnerability score because **available** quality is reduced by 2 of the 3 best arms being limited.

If you want a *different* scenario (taxed weak bullpen, fresh strong bullpen) for additional tests, add new fixtures — naming convention is `bullpen_state_<team>_<YYYY-MM-DD>.json`.

## Decisions baked in

1. **Trend label thresholds:** ±10% from season baseline → HEATING_UP / COOLING_OFF. ±30% → REGRESSION_RISK. Within ±10%, STABLE_STRONG vs STABLE_WEAK based on absolute baseline (HITTER_STRONG_OPS=.740, PITCHER_STRONG_ERA=3.80, TEAM_STRONG_RUNS_PER_GAME=4.7). All constants exported from the module — propose changes via PR if you'd like different thresholds.
2. **VOLATILE label is unused for now** — would need per-game variance, which we don't track yet. Documented as a Phase-later enhancement.
3. **Two reliever fixture conventions:** the standalone `reliever_form_alvarado_l20.json` exists as a one-off shape test. In practice you'll get reliever windows via the `BullpenState.relievers` list.
4. **Weighted form metric:** if you pass `{WindowKey.SEASON: x}` only, you get back `x` (the weight redistributes). That means even when L20/L10/L5 are insufficient, you get a sensible model probability.

## What's still NOT done

- No actual ingestion — the DB-backed builders will return `None` until Phase 7 fills `*_game_logs` with real data.
- No loader for pitcher/reliever form-window rows yet (only team + hitter); will add alongside Phase 7. You can mock around this in tests by constructing dataclasses directly.
- Bullpen `available_bullpen_quality` and `overall_bullpen_quality` definitions are yours to design — recent_form.py only handles per-reliever windows. Once you settle on a formula, document it in `docs/collab/interfaces/bullpen-availability-rules.md` so it lives next to the other interface contracts.

## Open question still pending from previous handoff

I asked whether Track A should handle JSON serialization of `supporting_factors` / `opposing_factors` / `uncertainty_flags` at the persistence boundary, so your code can stay pure with `List[str]`. Still my preference unless you push back. Reply via a new handoff.
