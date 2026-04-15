"""
Loads the pre-built sea distance matrix from CSV, and sea route waypoints
from JSON.  Falls back to Haversine × factor if CSV not found or port not
in matrix.

Usage:
    from data.sea_distances_loader import (
        load_distance_matrix, get_sea_distance_nm,
        load_route_waypoints, get_sea_route_coords,
    )
    load_distance_matrix()          # call once at startup
    load_route_waypoints()          # call once at startup
    nm = get_sea_distance_nm("Singapore", "Port Kelang")
    coords = get_sea_route_coords("Singapore", "Port Kelang")
"""

import os
import csv
import json
import math

_DISTANCE_MATRIX: dict[str, dict[str, float]] = {}
_CSV_LOADED = False

_ROUTE_WAYPOINTS: dict[str, list] = {}
_WAYPOINTS_LOADED = False

_DIR      = os.path.dirname(os.path.abspath(__file__))
_CSV_PATH  = os.path.join(_DIR, "port_sea_distances.csv")
_JSON_PATH = os.path.join(_DIR, "port_sea_routes.json")


# ── Distance matrix ───────────────────────────────────────────────────────────

def _haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float,
                  factor: float = 1.35) -> float:
    """Haversine great-circle distance in NM with routing correction factor."""
    R = 3440.065
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = (math.sin(dlat / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2)
    return round(2 * R * math.asin(math.sqrt(a)) * factor, 1)


def load_distance_matrix() -> bool:
    """
    Load pre-built CSV distance matrix into memory.
    Returns True if loaded successfully, False if file not found.
    Should be called once at application startup.
    """
    global _DISTANCE_MATRIX, _CSV_LOADED

    if _CSV_LOADED:
        return True

    if not os.path.exists(_CSV_PATH):
        return False

    with open(_CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        headers = next(reader)[1:]  # skip "origin" column header
        for row in reader:
            if not row:
                continue
            origin = row[0]
            _DISTANCE_MATRIX[origin] = {}
            for i, dest in enumerate(headers):
                try:
                    val = float(row[i + 1])
                    if val > 0:
                        _DISTANCE_MATRIX[origin][dest] = val
                except (ValueError, IndexError):
                    pass

    _CSV_LOADED = len(_DISTANCE_MATRIX) > 0
    return _CSV_LOADED


def is_loaded() -> bool:
    """Return True if the sea distance matrix is loaded."""
    return _CSV_LOADED


def get_sea_distance_nm(port_a: str, port_b: str,
                        port_coords: dict | None = None,
                        country_a: str = "",
                        country_b: str = "") -> float:
    """
    Return sea distance in NM between two ports.

    Resolution order:
      1. Pre-built matrix (exact match)
      2. Pre-built matrix (reverse lookup — symmetric)
      3. Haversine × factor using port_coords (if provided)
      4. Returns 0.0 if nothing available

    port_coords: dict of {port_name: (lat, lon)}
    country_a / country_b: used to choose Haversine correction factor
    """
    if port_a == port_b:
        return 0.0

    # 1. Forward lookup
    if _CSV_LOADED:
        dist = _DISTANCE_MATRIX.get(port_a, {}).get(port_b)
        if dist and dist > 0:
            return dist
        # 2. Reverse lookup
        dist_rev = _DISTANCE_MATRIX.get(port_b, {}).get(port_a)
        if dist_rev and dist_rev > 0:
            return dist_rev

    # 3. Haversine fallback
    if port_coords and port_a in port_coords and port_b in port_coords:
        lat1, lon1 = port_coords[port_a]
        lat2, lon2 = port_coords[port_b]
        factor = _routing_factor(country_a, country_b, lon1, lon2)
        return _haversine_nm(lat1, lon1, lat2, lon2, factor)

    return 0.0


def _routing_factor(country_a: str, country_b: str,
                    lon1: float, lon2: float) -> float:
    """Reproduction of data_processor.sea_distance() correction factors."""
    if country_a == "Indonesia" and country_b == "Indonesia":
        return 1.45
    if ("Indonesia" in (country_a, country_b) and
            "Philippines" in (country_a, country_b)):
        return 1.35
    if (lon1 < 105 or lon2 < 105) and (lon1 > 115 or lon2 > 115):
        return 1.50
    if "Bangladesh" in (country_a, country_b):
        return 1.40
    if "Sri Lanka" in (country_a, country_b):
        return 1.35
    if country_a == "Philippines" and country_b == "Philippines":
        return 1.30
    return 1.25


# ── Route waypoints ───────────────────────────────────────────────────────────

def load_route_waypoints() -> bool:
    """
    Load pre-built sea route waypoints from JSON into memory.
    Returns True if loaded successfully, False if file not found.
    Should be called once at application startup.
    """
    global _ROUTE_WAYPOINTS, _WAYPOINTS_LOADED

    if _WAYPOINTS_LOADED:
        return True

    if not os.path.exists(_JSON_PATH):
        return False

    with open(_JSON_PATH, encoding="utf-8") as f:
        _ROUTE_WAYPOINTS = json.load(f)

    _WAYPOINTS_LOADED = len(_ROUTE_WAYPOINTS) > 0
    return _WAYPOINTS_LOADED


def waypoints_loaded() -> bool:
    """Return True if the route waypoints JSON is loaded."""
    return _WAYPOINTS_LOADED


def get_sea_route_coords(port_a: str, port_b: str) -> list:
    """
    Return list of [lon, lat] waypoints for the real sea route between two
    ports.  Returns an empty list if waypoints are not available.

    The JSON stores both directions, so no coordinate reversal is needed here.
    """
    if not _WAYPOINTS_LOADED:
        return []

    key     = f"{port_a}|{port_b}"
    key_rev = f"{port_b}|{port_a}"

    coords = _ROUTE_WAYPOINTS.get(key)
    if coords:
        return coords

    # Try reverse direction and flip the coordinate list
    coords_rev = _ROUTE_WAYPOINTS.get(key_rev)
    if coords_rev:
        return list(reversed(coords_rev))

    return []
