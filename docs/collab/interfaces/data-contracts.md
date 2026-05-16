# Data contracts between Track A and Track B

**Status:** STRAWMAN — drafted by Track A. Track B (Jack) should review and propose changes via PR.

This file defines the Python dataclass shapes that flow between tracks. Track A produces these; Track B consumes them. Both sides build against the same shapes so we can work in parallel — Track B uses fixture JSON files (see `tests/fixtures/`) until Track A's query helpers land.

## Ground rules

- All dataclasses live in `app/contracts.py` (created in Phase 2). Both tracks import from there.
- Use `@dataclass(frozen=True)` — these are value objects.
- Dates as `datetime.date`. Timestamps as timezone-aware `datetime`.
- Rate stats stored as decimals, not percentages: `.275` not `27.5`. Document units in field comments.
- Optional fields use `Optional[T]` with `None` as the "we don't have this yet" value. **Never fabricate defaults.**
- If a window has insufficient samples, the dataclass should still exist but with `sample_size` set and `insufficient_sample: bool = True`. Track B's job to decide how to handle.

## Window key

Used throughout. Defined once:

```python
class WindowKey(str, Enum):
    SEASON = "season"
    L20 = "l20"   # last 20 games / appearances
    L10 = "l10"
    L5  = "l5"
    LAST_10_STARTS = "last_10_starts"  # starters only
    LAST_5_STARTS  = "last_5_starts"
```

## Trend label

```python
class TrendLabel(str, Enum):
    HEATING_UP        = "heating_up"
    COOLING_OFF       = "cooling_off"
    STABLE_STRONG     = "stable_strong"
    STABLE_WEAK       = "stable_weak"
    VOLATILE          = "volatile"
    REGRESSION_RISK   = "regression_risk"
    SMALL_SAMPLE_WARN = "small_sample_warning"
```

---

## TeamFormWindow

```python
@dataclass(frozen=True)
class TeamFormWindow:
    team_id: int
    team_abbr: str           # "PHI", "NYM"
    window: WindowKey
    games: int               # actual game count in this window
    runs_per_game: float
    runs_allowed_per_game: float
    team_ops: float          # decimal, e.g. .742
    team_woba: Optional[float]
    stolen_bases: int
    caught_stealing: int
    stolen_base_attempts: int
    stolen_base_success_rate: Optional[float]
    lineup_quality_score: Optional[float]  # avg estimated wOBA of top 6 PA leaders
    record_wins: int
    record_losses: int
    trend_label: TrendLabel
    insufficient_sample: bool = False
    as_of_date: date         # date the window ends
```

**Open question for Jack:** do we need run differential as its own field, or is `runs_per_game - runs_allowed_per_game` fine to compute downstream?

---

## PlayerFormWindow (hitters)

```python
@dataclass(frozen=True)
class PlayerFormWindow:
    player_id: int
    player_name: str
    team_id: int
    window: WindowKey
    games: int
    plate_appearances: int
    batting_avg: float
    on_base_pct: float
    slugging_pct: float
    ops: float
    woba: Optional[float]
    home_runs: int
    strikeouts: int
    walks: int
    trend_label: TrendLabel
    insufficient_sample: bool = False
    as_of_date: date
```

---

## PitcherFormWindow (starters)

```python
@dataclass(frozen=True)
class PitcherFormWindow:
    pitcher_id: int
    pitcher_name: str
    team_id: int
    window: WindowKey            # SEASON | LAST_10_STARTS | LAST_5_STARTS
    starts: int
    innings_pitched: float
    era: float
    fip: Optional[float]
    xfip: Optional[float]
    babip: Optional[float]
    whip: float
    k_per_9: float
    bb_per_9: float
    hr_per_9: float
    avg_pitches_per_start: Optional[float]
    avg_innings_per_start: float
    trend_label: TrendLabel
    insufficient_sample: bool = False
    as_of_date: date
```

---

## RelieverFormWindow

```python
@dataclass(frozen=True)
class RelieverFormWindow:
    pitcher_id: int
    pitcher_name: str
    team_id: int
    role: Literal["closer", "setup", "high_leverage", "middle", "long", "low_leverage"]
    window: WindowKey            # SEASON | L20 | L10 | L5
    appearances: int
    innings_pitched: float
    era: float
    fip: Optional[float]
    whip: float
    k_per_9: float
    bb_per_9: float
    inherited_runners_scored_pct: Optional[float]
    trend_label: TrendLabel
    insufficient_sample: bool = False
    as_of_date: date
```

---

## RelieverUsage

Daily usage record — drives fatigue scoring. One per (reliever, game).

```python
@dataclass(frozen=True)
class RelieverUsage:
    pitcher_id: int
    pitcher_name: str
    team_id: int
    role: Literal["closer", "setup", "high_leverage", "middle", "long", "low_leverage"]
    game_date: date
    pitches: int
    innings: float
    appeared: bool
```

---

## BullpenState

The thing Track B's bullpen scoring functions take as input. Composed by Track A from the underlying usage + form data.

```python
@dataclass(frozen=True)
class BullpenState:
    team_id: int
    team_abbr: str
    as_of_date: date              # date OF THE GAME being scored (today)

    # Yesterday's workload (drives fatigue)
    yesterday_total_innings: float
    yesterday_total_pitches: int
    yesterday_relievers_used: int
    closer_pitched_yesterday: bool
    high_leverage_pitched_yesterday: List[int]  # pitcher_ids

    # Rest patterns over recent days
    back_to_back_relievers: List[int]   # pitcher_ids who pitched both of last 2 days
    three_in_four_relievers: List[int]  # pitched 3 of last 4 days

    # Per-reliever form (all windows for each rostered reliever)
    relievers: List[RelieverFormWindow]   # multiple windows per reliever; group by pitcher_id

    # Recent usage history (last ~5 days) for context
    recent_usage: List[RelieverUsage]
```

**Notes for Jack:**

- Fatigue formula in PROJECT_BRIEF.md operates entirely on the first block of fields (yesterday's workload + rest patterns) plus the closer/setup flags. Pure computation, no I/O.
- Quality scoring derives from `relievers` (the form windows). Define your own weighting; the brief doesn't fix one.
- "Available quality" needs availability labels (`unavailable`, `limited`, `available`). Suggested rule: closer pitched yesterday → limited; reliever in `back_to_back_relievers` and threw 25+ pitches → unavailable. Refine and document in `interfaces/bullpen-availability-rules.md` when you build it.

---

## GameContext

Everything Track B needs to analyze a single game.

```python
@dataclass(frozen=True)
class GameContext:
    game_id: int
    game_date: date
    game_time_utc: datetime
    home_team_id: int
    away_team_id: int
    home_team_abbr: str
    away_team_abbr: str
    venue: str
    home_probable_starter_id: Optional[int]
    away_probable_starter_id: Optional[int]
    is_doubleheader: bool
    game_number: int  # 1 or 2 in a DH, else 1
```

Track B fetches form/bullpen/odds keyed off the IDs in here.

---

## OddsSnapshot

```python
@dataclass(frozen=True)
class OddsSnapshot:
    game_id: int
    bookmaker: str               # "draftkings", "fanduel", etc.
    market: Literal["moneyline", "spread", "total", "f5_moneyline", "f5_total", "team_total"]
    selection: str               # "home", "away", "over", "under", or team abbr
    line: Optional[float]        # null for moneyline; -1.5, 8.5, etc. otherwise
    american_odds: int           # -115, +130
    captured_at: datetime        # tz-aware
```

---

## WeatherSnapshot

```python
@dataclass(frozen=True)
class WeatherSnapshot:
    game_id: int
    temperature_f: float
    wind_speed_mph: float
    wind_direction_deg: int      # 0-359, meteorological
    precipitation_chance: float  # 0.0 - 1.0
    humidity_pct: float
    is_dome: bool                # if dome, other fields may be None
    captured_at: datetime
```

---

## BetEvaluation (Track B output)

For completeness — this is what Track B's market verification produces. Track A stores it.

```python
@dataclass(frozen=True)
class BetEvaluation:
    game_id: int
    market: str
    selection: str
    current_odds: int
    implied_probability: float
    estimated_probability: float
    edge: float
    confidence_score: float           # 0.0 - 1.0
    evidence_quality_score: float     # 0.0 - 1.0
    recommendation: Literal["strong_lean", "lean", "pass", "avoid", "need_more_info"]
    supporting_factors: List[str]
    opposing_factors: List[str]
    uncertainty_flags: List[str]
    what_would_change_the_answer: str
    generated_at: datetime
```

---

## Fixtures

Track A will commit example JSON files under `tests/fixtures/` matching every shape above, so Track B can write tests without running ingestion:

```
tests/fixtures/
├── team_form_phi_l10.json
├── pitcher_form_wheeler_season.json
├── reliever_form_alvarado_l20.json
├── bullpen_state_phi_2026-05-15.json
├── game_context_phi_vs_nym_2026-05-15.json
├── odds_snapshot_phi_vs_nym.json
└── weather_snapshot_phi_vs_nym.json
```

Track B should write tests that load these fixtures via a small helper (`tests/fixtures/__init__.py`) and assert on score outputs.

---

## Change process

1. Either track proposes a change via PR editing this file.
2. Tag the other track for review.
3. Bump the version note below when the change merges.
4. Update fixtures and any consumer code in **separate** PRs.

**Version:** 0.1 (strawman, 2026-05-15)
