"""Cross-track data contracts.

These dataclasses are the seam between Track A (data platform) and
Track B (analysis & output). Track A produces them; Track B consumes them.

Spec lives in `docs/collab/interfaces/data-contracts.md`. Update the spec
*and* this file together when a shape changes — both sides import from
here, and any breaking change requires a PR review from the other track.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import List, Literal, Optional


class WindowKey(str, Enum):
    SEASON = "season"
    L20 = "l20"
    L10 = "l10"
    L5 = "l5"
    LAST_10_STARTS = "last_10_starts"
    LAST_5_STARTS = "last_5_starts"


class TrendLabel(str, Enum):
    HEATING_UP = "heating_up"
    COOLING_OFF = "cooling_off"
    STABLE_STRONG = "stable_strong"
    STABLE_WEAK = "stable_weak"
    VOLATILE = "volatile"
    REGRESSION_RISK = "regression_risk"
    SMALL_SAMPLE_WARN = "small_sample_warning"


RelieverRole = Literal[
    "closer", "setup", "high_leverage", "middle", "long", "low_leverage"
]

Recommendation = Literal[
    "strong_lean", "lean", "pass", "avoid", "need_more_info"
]

Market = Literal[
    "moneyline", "spread", "total", "f5_moneyline", "f5_total", "team_total"
]


@dataclass(frozen=True)
class TeamFormWindow:
    team_id: int
    team_abbr: str
    window: WindowKey
    games: int
    runs_per_game: float
    runs_allowed_per_game: float
    team_ops: float
    record_wins: int
    record_losses: int
    trend_label: TrendLabel
    as_of_date: date
    team_woba: Optional[float] = None
    stolen_bases: int = 0
    caught_stealing: int = 0
    stolen_base_attempts: int = 0
    stolen_base_success_rate: Optional[float] = None
    lineup_quality_score: Optional[float] = None
    insufficient_sample: bool = False


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
    home_runs: int
    strikeouts: int
    walks: int
    trend_label: TrendLabel
    as_of_date: date
    woba: Optional[float] = None
    platoon_woba_vs_l: Optional[float] = None
    platoon_woba_vs_r: Optional[float] = None
    insufficient_sample: bool = False


@dataclass(frozen=True)
class PitcherFormWindow:
    pitcher_id: int
    pitcher_name: str
    team_id: int
    window: WindowKey
    starts: int
    innings_pitched: float
    era: float
    whip: float
    k_per_9: float
    bb_per_9: float
    hr_per_9: float
    avg_innings_per_start: float
    trend_label: TrendLabel
    as_of_date: date
    fip: Optional[float] = None
    xfip: Optional[float] = None
    babip: Optional[float] = None
    avg_pitches_per_start: Optional[float] = None
    insufficient_sample: bool = False


@dataclass(frozen=True)
class RelieverFormWindow:
    pitcher_id: int
    pitcher_name: str
    team_id: int
    role: RelieverRole
    window: WindowKey
    appearances: int
    innings_pitched: float
    era: float
    whip: float
    k_per_9: float
    bb_per_9: float
    trend_label: TrendLabel
    as_of_date: date
    fip: Optional[float] = None
    inherited_runners_scored_pct: Optional[float] = None
    insufficient_sample: bool = False


@dataclass(frozen=True)
class RelieverUsage:
    pitcher_id: int
    pitcher_name: str
    team_id: int
    role: RelieverRole
    game_date: date
    pitches: int
    innings: float
    appeared: bool


@dataclass(frozen=True)
class BullpenState:
    team_id: int
    team_abbr: str
    as_of_date: date
    yesterday_total_innings: float
    yesterday_total_pitches: int
    yesterday_relievers_used: int
    closer_pitched_yesterday: bool
    high_leverage_pitched_yesterday: List[int]
    back_to_back_relievers: List[int]
    three_in_four_relievers: List[int]
    relievers: List[RelieverFormWindow] = field(default_factory=list)
    recent_usage: List[RelieverUsage] = field(default_factory=list)


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
    is_doubleheader: bool
    game_number: int
    home_probable_starter_id: Optional[int] = None
    away_probable_starter_id: Optional[int] = None


@dataclass(frozen=True)
class OddsSnapshot:
    game_id: int
    bookmaker: str
    market: Market
    selection: str
    american_odds: int
    captured_at: datetime
    line: Optional[float] = None


@dataclass(frozen=True)
class WeatherSnapshot:
    game_id: int
    temperature_f: Optional[float]
    wind_speed_mph: Optional[float]
    wind_direction_deg: Optional[int]
    precipitation_chance: Optional[float]
    humidity_pct: Optional[float]
    is_dome: bool
    captured_at: datetime


@dataclass(frozen=True)
class BetEvaluation:
    game_id: int
    market: str
    selection: str
    current_odds: int
    implied_probability: float
    estimated_probability: float
    edge: float
    confidence_score: float
    evidence_quality_score: float
    recommendation: Recommendation
    supporting_factors: List[str]
    opposing_factors: List[str]
    uncertainty_flags: List[str]
    what_would_change_the_answer: str
    generated_at: datetime
