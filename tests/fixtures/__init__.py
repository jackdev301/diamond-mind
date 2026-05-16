"""Fixture loader.

Each JSON file under this folder represents a snapshot of one of the
dataclasses in `app.contracts`. The loader hydrates the JSON back into
the right dataclass so tests can work against realistic shapes without
hitting a database.

Track B (Jack) uses these to develop betting / bullpen / report code
without waiting on Track A's ingestion to land.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Type, TypeVar

from app.contracts import (
    BullpenState,
    GameContext,
    OddsSnapshot,
    PitcherFormWindow,
    PlayerFormWindow,
    RelieverFormWindow,
    RelieverUsage,
    TeamFormWindow,
    TrendLabel,
    WeatherSnapshot,
    WindowKey,
)


FIXTURES_DIR = Path(__file__).parent

T = TypeVar("T")


def _build(
    cls: Type[T],
    data: dict,
    date_fields: set[str] = frozenset(),
    datetime_fields: set[str] = frozenset(),
    nested: dict[str, Type] | None = None,
) -> T:
    out: dict[str, Any] = {}
    for key, val in data.items():
        if val is None:
            out[key] = None
        elif key in date_fields:
            out[key] = date.fromisoformat(val)
        elif key in datetime_fields:
            out[key] = datetime.fromisoformat(val)
        elif key == "window":
            out[key] = WindowKey(val)
        elif key == "trend_label":
            out[key] = TrendLabel(val)
        elif nested and key in nested:
            out[key] = [_load_typed(nested[key], item) for item in val]
        else:
            out[key] = val
    return cls(**out)


def _load_typed(cls: Type[T], data: dict) -> T:
    if cls in (TeamFormWindow, PlayerFormWindow, PitcherFormWindow, RelieverFormWindow):
        return _build(cls, data, date_fields={"as_of_date"})
    if cls is RelieverUsage:
        return _build(cls, data, date_fields={"game_date"})
    if cls is BullpenState:
        return _build(
            cls, data,
            date_fields={"as_of_date"},
            nested={"relievers": RelieverFormWindow, "recent_usage": RelieverUsage},
        )
    if cls is GameContext:
        return _build(
            cls, data,
            date_fields={"game_date"},
            datetime_fields={"game_time_utc"},
        )
    if cls is OddsSnapshot:
        return _build(cls, data, datetime_fields={"captured_at"})
    if cls is WeatherSnapshot:
        return _build(cls, data, datetime_fields={"captured_at"})
    raise TypeError(f"No fixture loader for {cls.__name__}")


def load_fixture(name: str, cls: Type[T]) -> T:
    path = FIXTURES_DIR / f"{name}.json"
    with path.open() as f:
        data = json.load(f)
    return _load_typed(cls, data)
