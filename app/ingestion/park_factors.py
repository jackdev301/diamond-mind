"""Multi-year regressed park factors for all 30 MLB venues.

Sources: FanGraphs 3-year regressed park factors (2022-2024).
Scale: 100 = neutral. >100 = hitter-friendly, <100 = pitcher-friendly.
All factors regressed 50% toward 100 for single-season stability.

Separate factors for:
  - runs (overall run environment)
  - hr   (home run rate)
  - hits (singles + hits rate)
"""
from __future__ import annotations

from typing import Optional
from dataclasses import dataclass


@dataclass(frozen=True)
class ParkFactor:
    venue: str
    runs: float   # 100 = neutral
    hr: float
    hits: float
    is_dome: bool = False


# 3-year regressed, 50% shrinkage toward 100
_PARK_FACTORS: list[ParkFactor] = [
    ParkFactor("Coors Field",                  runs=115.0, hr=112.0, hits=112.0),
    ParkFactor("Great American Ball Park",     runs=106.0, hr=110.0, hits=104.0),
    ParkFactor("Fenway Park",                  runs=105.0, hr=100.0, hits=107.0),
    ParkFactor("Citizens Bank Park",           runs=105.0, hr=108.0, hits=103.0),
    ParkFactor("Yankee Stadium",               runs=104.0, hr=112.0, hits=101.0),
    ParkFactor("Wrigley Field",                runs=104.0, hr=104.0, hits=103.0),
    ParkFactor("Globe Life Field",             runs=103.0, hr=105.0, hits=102.0, is_dome=True),
    ParkFactor("American Family Field",        runs=103.0, hr=106.0, hits=101.0),
    ParkFactor("Guaranteed Rate Field",        runs=103.0, hr=106.0, hits=101.0),
    ParkFactor("Kauffman Stadium",             runs=102.0, hr=100.0, hits=103.0),
    ParkFactor("Angel Stadium",                runs=101.0, hr=100.0, hits=101.0),
    ParkFactor("Truist Park",                  runs=101.0, hr=102.0, hits=101.0),
    ParkFactor("Minute Maid Park",             runs=101.0, hr=103.0, hits=100.0, is_dome=False),
    ParkFactor("Target Field",                 runs=100.0, hr=98.0,  hits=100.0),
    ParkFactor("Busch Stadium",                runs=99.0,  hr=96.0,  hits=100.0),
    ParkFactor("Dodger Stadium",               runs=99.0,  hr=99.0,  hits=99.0),
    ParkFactor("PNC Park",                     runs=99.0,  hr=97.0,  hits=100.0),
    ParkFactor("Oriole Park at Camden Yards",  runs=99.0,  hr=101.0, hits=99.0),
    ParkFactor("Rogers Centre",                runs=99.0,  hr=102.0, hits=98.0, is_dome=True),
    ParkFactor("Comerica Park",                runs=98.0,  hr=96.0,  hits=99.0),
    ParkFactor("T-Mobile Park",                runs=97.0,  hr=95.0,  hits=98.0),
    ParkFactor("Oracle Park",                  runs=97.0,  hr=93.0,  hits=98.0),
    ParkFactor("Citi Field",                   runs=97.0,  hr=96.0,  hits=98.0),
    ParkFactor("Progressive Field",            runs=97.0,  hr=97.0,  hits=98.0),
    ParkFactor("Nationals Park",               runs=97.0,  hr=97.0,  hits=98.0),
    ParkFactor("Petco Park",                   runs=96.0,  hr=93.0,  hits=97.0),
    ParkFactor("Chase Field",                  runs=96.0,  hr=95.0,  hits=97.0, is_dome=False),
    ParkFactor("loanDepot park",               runs=95.0,  hr=94.0,  hits=96.0, is_dome=True),
    ParkFactor("Tropicana Field",              runs=95.0,  hr=93.0,  hits=96.0, is_dome=True),
    ParkFactor("Oakland Coliseum",             runs=94.0,  hr=91.0,  hits=96.0),
]

_BY_VENUE: dict[str, ParkFactor] = {pf.venue: pf for pf in _PARK_FACTORS}
_NEUTRAL = ParkFactor(venue="neutral", runs=100.0, hr=100.0, hits=100.0)


def get_park_factor(venue: Optional[str]) -> ParkFactor:
    """Return the ParkFactor for a venue name, or neutral if unknown."""
    if not venue:
        return _NEUTRAL
    # Exact match first
    if venue in _BY_VENUE:
        return _BY_VENUE[venue]
    # Partial match fallback (handles slight name variations)
    venue_lower = venue.lower()
    for name, pf in _BY_VENUE.items():
        if name.lower() in venue_lower or venue_lower in name.lower():
            return pf
    return _NEUTRAL


def run_factor(venue: Optional[str]) -> float:
    """Convenience: returns runs park factor as a multiplier (1.0 = neutral)."""
    return get_park_factor(venue).runs / 100.0


def hr_factor(venue: Optional[str]) -> float:
    return get_park_factor(venue).hr / 100.0
