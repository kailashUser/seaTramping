"""
One-time script to build the sea distance matrix and route waypoints
for all ports in PORT_COORDS.

Run this once from the project root:
    python data/build_distance_matrix.py

Outputs:
    data/port_sea_distances.csv   — NxN symmetric distance matrix (NM)
    data/port_sea_routes.json     — route waypoints for every port pair

Uses the searoute library (EU JRC maritime routing network, free, no API key).
For routes that cross the Indonesian/Philippine archipelago, forced intermediate
waypoints are used to ensure the route follows real strait passages rather than
cutting through land.
Falls back to Haversine × 1.35 (empty waypoints []) when searoute fails.
Approximate runtime: 5-15 minutes depending on CPU.
"""

import csv
import json
import math
import os
import sys
import time

try:
    import searoute as sr
    HAS_SEAROUTE = True
except ImportError:
    HAS_SEAROUTE = False
    print("ERROR: searoute not installed. Run: pip install searoute")
    sys.exit(1)

# Add project root to path so we can import port_coordinates
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.port_coordinates import PORT_COORDS  # {port: (lat, lon)}

_DIR        = os.path.dirname(os.path.abspath(__file__))
OUTPUT_CSV  = os.path.join(_DIR, "port_sea_distances.csv")
OUTPUT_JSON = os.path.join(_DIR, "port_sea_routes.json")


# ── Strait passage waypoints ──────────────────────────────────────────────────
# [lon, lat] format (same as searoute input)

SEA_FORCED_WAYPOINTS = {
    "malacca":  [103.5,   1.2],   # Malacca Strait southern approach
    "sunda":    [105.8,  -6.0],   # Sunda Strait (Java–Sumatra)
    "karimata": [108.5,  -1.5],   # Karimata Strait (Kalimantan–Sumatra)
    "makassar": [117.5,  -1.0],   # Makassar Strait
    "lombok":   [115.7,  -8.5],   # Lombok Strait
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def haversine_nm(lat1, lon1, lat2, lon2, factor=1.35):
    """Haversine great-circle distance in NM with routing correction factor."""
    R = 3440.065
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    return round(2 * R * math.asin(math.sqrt(a)) * factor, 1)


def _haversine_fallback(origin_lonlat, dest_lonlat, factor=1.35):
    """Return Haversine NM given [lon, lat] pairs."""
    lon1, lat1 = origin_lonlat
    lon2, lat2 = dest_lonlat
    return haversine_nm(lat1, lon1, lat2, lon2, factor)


def _direct_route(origin_lonlat, dest_lonlat):
    """
    Single searoute call. Returns (nm, coords) or (None, []) on failure.
    Uses units='nm' and append_orig_dest=True for cleaner waypoints.
    """
    try:
        route = sr.searoute(
            origin_lonlat,
            dest_lonlat,
            units="nm",
            append_orig_dest=True,
        )
        nm     = float(route['properties']['length'])
        coords = route['geometry']['coordinates']   # list of [lon, lat]
        if nm > 0 and len(coords) >= 2:
            return round(nm, 1), coords
    except Exception:
        pass
    return None, []


def _pick_forced_waypoints(lon1, lat1, lon2, lat2):
    """
    Return a list of intermediate [lon, lat] waypoints for routes that
    cross the Indonesian/Philippine archipelago.  Empty list = no forcing.

    Logic:
      1. Indian Ocean (lon < 100) → anywhere east of Malacca: add Malacca waypoint.
      2. West of archipelago (lon < 106) → East Indonesia / Philippines (lon > 117):
           add Karimata waypoint (Java Sea passage).
      3. Central (106 ≤ lon ≤ 112) → Far-east (lon > 120): add Makassar waypoint.
      4. Java-side to Lombok/Bali area → Eastern Indonesia: add Lombok waypoint.
    """
    lo_min = min(lon1, lon2)
    lo_max = max(lon1, lon2)
    la_dest = lat2  # latitude of destination

    wps = []

    # 1. Route from Indian Ocean side needs Malacca passage
    if lo_min < 100 and lo_max > 103:
        wps.append(SEA_FORCED_WAYPOINTS["malacca"])
        # Also need Karimata if going all the way east
        if lo_max > 117:
            wps.append(SEA_FORCED_WAYPOINTS["karimata"])
        return wps

    # 2. West-side to Eastern Indonesia/Philippines
    if lo_min < 106 and lo_max > 117:
        if la_dest < -2:
            # Eastern Indonesia south of equator — Karimata then Makassar
            wps.append(SEA_FORCED_WAYPOINTS["karimata"])
            wps.append(SEA_FORCED_WAYPOINTS["makassar"])
        else:
            # Philippines or north — Karimata strait (Java Sea)
            wps.append(SEA_FORCED_WAYPOINTS["karimata"])
        return wps

    # 3. Central Java/Kalimantan to far-east Sulawesi/Philippines
    if 106 <= lo_min and lo_min < 113 and lo_max > 120:
        wps.append(SEA_FORCED_WAYPOINTS["makassar"])
        return wps

    # 4. Java ports (lon ~107-114) to Eastern Indonesia via Lombok
    if 107 <= lo_min and lo_min <= 114 and lo_max > 115 and lo_max <= 120:
        wps.append(SEA_FORCED_WAYPOINTS["lombok"])
        return wps

    return []


def _route_via_waypoints(origin_lonlat, mid_points, dest_lonlat):
    """
    Route from origin through forced intermediate waypoints to destination.
    Chains multiple searoute calls and concatenates coordinates.
    Returns (nm, coords) or (None, []) if any segment fails.
    """
    all_points = [origin_lonlat] + mid_points + [dest_lonlat]
    total_nm   = 0.0
    all_coords = []

    for i in range(len(all_points) - 1):
        seg_nm, seg_coords = _direct_route(all_points[i], all_points[i + 1])
        if seg_nm is None or not seg_coords:
            return None, []
        total_nm += seg_nm
        if i == 0:
            all_coords.extend(seg_coords)
        else:
            # Skip duplicate point at junction (already added as last of prev seg)
            all_coords.extend(seg_coords[1:])

    if total_nm > 0 and len(all_coords) >= 3:
        return round(total_nm, 1), all_coords
    return None, []


def get_sea_distance_and_route(origin_lonlat, dest_lonlat):
    """
    Return (nm, coords) for the sea route between two ports.

    Strategy:
      1. Try direct searoute call.
      2. If result has < 3 waypoints (likely a bad/land-crossing route),
         try again with forced strait waypoints.
      3. If forced-waypoint route also fails, fall back to Haversine (no waypoints).

    origin_lonlat / dest_lonlat: [lon, lat]
    Returns:
        nm:     float — distance in nautical miles
        coords: list of [lon, lat] waypoints, or [] on fallback
    """
    lon1, lat1 = origin_lonlat
    lon2, lat2 = dest_lonlat

    # 1. Try direct route
    nm, coords = _direct_route(origin_lonlat, dest_lonlat)

    # 2. If too few waypoints, the route may have gone over land — try forced
    if nm is None or len(coords) < 3:
        forced = _pick_forced_waypoints(lon1, lat1, lon2, lat2)
        if forced:
            nm_f, coords_f = _route_via_waypoints(origin_lonlat, forced, dest_lonlat)
            if nm_f is not None and len(coords_f) >= 3:
                return nm_f, coords_f

        # Direct route returned valid NM but sparse waypoints — accept it
        if nm is not None and nm > 0:
            return nm, coords

        # Total failure — haversine fallback
        return _haversine_fallback(origin_lonlat, dest_lonlat), []

    # Direct route is good — but check if we should prefer a forced-waypoint
    # route for known problematic corridor pairs (it will be more accurate)
    forced = _pick_forced_waypoints(lon1, lat1, lon2, lat2)
    if forced:
        nm_f, coords_f = _route_via_waypoints(origin_lonlat, forced, dest_lonlat)
        if nm_f is not None and len(coords_f) >= 3:
            # Use forced route if it has substantially more waypoints (more detailed)
            # or if the direct route looks suspiciously short
            if len(coords_f) > len(coords) or nm_f > nm * 1.05:
                return nm_f, coords_f

    return nm, coords


# ── Main matrix builder ───────────────────────────────────────────────────────

def build_matrix():
    ports  = sorted(PORT_COORDS.keys())
    n      = len(ports)
    n_pairs = n * (n - 1) // 2
    print(f"Building {n}×{n} sea distance matrix ({n_pairs:,} unique pairs)...")
    print(f"Distance CSV  : {OUTPUT_CSV}")
    print(f"Waypoints JSON: {OUTPUT_JSON}")
    print()

    matrix    = {p: {} for p in ports}   # {origin: {dest: nm}}
    waypoints = {}                        # {"A|B": [[lon,lat],...], "B|A": reversed}
    done           = 0
    fallback_count = 0
    forced_count   = 0
    start_time     = time.time()

    for i, port_a in enumerate(ports):
        lat1, lon1 = PORT_COORDS[port_a]
        for j, port_b in enumerate(ports):
            if port_a == port_b:
                matrix[port_a][port_b] = 0.0
                continue

            # Use symmetry — compute once, mirror
            if port_b in matrix[port_a]:
                continue
            if port_a in matrix[port_b]:
                nm = matrix[port_b][port_a]
                matrix[port_a][port_b] = nm
                # Flip already-stored waypoints for the reverse direction
                rev_key = f"{port_b}|{port_a}"
                if rev_key in waypoints:
                    waypoints[f"{port_a}|{port_b}"] = list(reversed(waypoints[rev_key]))
                continue

            lat2, lon2 = PORT_COORDS[port_b]

            nm, coords = get_sea_distance_and_route([lon1, lat1], [lon2, lat2])

            if nm is None or nm <= 0:
                nm = haversine_nm(lat1, lon1, lat2, lon2, factor=1.35)
                coords = []
                fallback_count += 1
            elif not coords:
                fallback_count += 1

            # Track how many routes used forced waypoints
            forced = _pick_forced_waypoints(lon1, lat1, lon2, lat2)
            if forced and coords:
                forced_count += 1

            matrix[port_a][port_b] = nm
            matrix[port_b][port_a] = nm

            if coords:
                key_fwd = f"{port_a}|{port_b}"
                key_rev = f"{port_b}|{port_a}"
                waypoints[key_fwd] = coords
                waypoints[key_rev] = list(reversed(coords))

            done += 1
            if done % 200 == 0:
                elapsed   = time.time() - start_time
                rate      = done / elapsed
                remaining = (n_pairs - done) / max(rate, 1)
                pct       = done * 100 // n_pairs
                print(f"  {done:,}/{n_pairs:,} pairs ({pct}%) — "
                      f"~{remaining / 60:.1f} min remaining  "
                      f"[fallbacks: {fallback_count}  forced strait: {forced_count}]")

            time.sleep(0.02)  # gentle pacing

    # ── Write distance CSV ────────────────────────────────────────────────────
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["origin"] + ports)
        for origin in ports:
            row = [origin] + [matrix[origin].get(dest, 0.0) for dest in ports]
            writer.writerow(row)

    # ── Write waypoints JSON ──────────────────────────────────────────────────
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(waypoints, f, separators=(',', ':'))   # compact — file can be large

    elapsed_total = time.time() - start_time
    print()
    print(f"Done in {elapsed_total / 60:.1f} minutes.")
    print(f"  {n} ports × {n} ports = {n*n} cells")
    print(f"  Haversine fallbacks:  {fallback_count} pairs")
    print(f"  Forced strait routes: {forced_count} pairs")
    print(f"  Waypoints saved:      {len(waypoints)//2:,} routes ({len(waypoints):,} directions)")
    print(f"  CSV  -> {OUTPUT_CSV}")
    print(f"  JSON -> {OUTPUT_JSON}")


if __name__ == "__main__":
    build_matrix()
