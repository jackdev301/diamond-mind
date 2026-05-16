"""Latitude/longitude for every current MLB venue.

Used by the weather client. Dome venues are listed in weather_api._DOME_VENUES
and will short-circuit before coordinates are needed.
"""

from typing import Optional, Tuple

# (lat, lon) — WGS84
VENUE_COORDS: dict[str, Tuple[float, float]] = {
    "Angel Stadium": (33.8003, -117.8827),
    "Busch Stadium": (38.6226, -90.1928),
    "Chase Field": (33.4455, -112.0667),
    "Citizens Bank Park": (39.9061, -75.1665),
    "Citi Field": (40.7571, -73.8458),
    "Comerica Park": (42.3390, -83.0485),
    "Coors Field": (39.7559, -104.9942),
    "Dodger Stadium": (34.0739, -118.2400),
    "Fenway Park": (42.3467, -71.0972),
    "Globe Life Field": (32.7473, -97.0825),
    "Great American Ball Park": (39.0979, -84.5082),
    "Guaranteed Rate Field": (41.8300, -87.6339),
    "Kauffman Stadium": (39.0517, -94.4803),
    "loanDepot park": (25.7781, -80.2197),
    "American Family Field": (43.0280, -87.9712),
    "Minute Maid Park": (29.7573, -95.3555),
    "Nationals Park": (38.8730, -77.0074),
    "Oakland Coliseum": (37.7516, -122.2005),
    "Oracle Park": (37.7786, -122.3893),
    "Oriole Park at Camden Yards": (39.2838, -76.6218),
    "Petco Park": (32.7076, -117.1570),
    "PNC Park": (40.4469, -80.0057),
    "Progressive Field": (41.4962, -81.6852),
    "Rogers Centre": (43.6414, -79.3894),
    "T-Mobile Park": (47.5914, -122.3325),
    "Target Field": (44.9817, -93.2781),
    "Tropicana Field": (27.7682, -82.6534),
    "Truist Park": (33.8908, -84.4678),
    "Wrigley Field": (41.9484, -87.6553),
    "Yankee Stadium": (40.8296, -73.9262),
}


def get_coords(venue: str) -> Optional[Tuple[float, float]]:
    return VENUE_COORDS.get(venue)
