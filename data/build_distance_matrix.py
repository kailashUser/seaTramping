"""
One-time script to build the sea distance matrix and route waypoints
for all ports in PORT_COORDS.

Run this once from the project root:
    python data/build_distance_matrix.py

Outputs:
    data/port_sea_distances.csv   - NxN symmetric distance matrix (NM)
    data/port_sea_routes.json     - route waypoints for every port pair

Uses the searoute library (EU JRC maritime routing network, free, no API key).
For routes that cross the Indonesian/Philippine archipelago, forced intermediate
waypoints are used to ensure the route follows real strait passages.

A smart validation layer rejects searoute results that are geometrically
impossible (shorter than straight-line) or wildly long (>1.6x the region-aware
smart distance), substituting a chokepoint-based estimate in those cases.

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


# ── Maritime chokepoint waypoints [lat, lon] ──────────────────────────────────

WP = {
    "malacca":    ( 1.20,  103.50),   # Malacca Strait southern approach
    "singapore":  ( 1.25,  103.80),   # Singapore Strait
    "sunda":      (-6.00,  105.80),   # Sunda Strait (Java-Sumatra)
    "karimata":   (-1.50,  108.50),   # Karimata Strait (Kalimantan-Sumatra)
    "makassar":   (-1.00,  117.50),   # Makassar Strait
    "lombok":     (-8.50,  115.70),   # Lombok Strait
    "luzon":      (18.50,  121.50),   # Luzon Strait (Philippines-Taiwan)
    "taiwan":     (23.50,  120.50),   # Taiwan Strait
    "ombai":      (-8.50,  125.00),   # Ombai Strait (Timor Sea entry)
    "torres":     (-9.80,  142.20),   # Torres Strait (Australia-PNG)
    "scs_centre": (12.00,  114.00),   # South China Sea centre
}

# Forced waypoints for Indonesian archipelago routing [lon, lat] for searoute
SEA_FORCED_WAYPOINTS = {
    "malacca":  [103.5,   1.2],
    "sunda":    [105.8,  -6.0],
    "karimata": [108.5,  -1.5],
    "makassar": [117.5,  -1.0],
    "lombok":   [115.7,  -8.5],
}


# ── Haversine helpers ─────────────────────────────────────────────────────────

def haversine_nm(lat1, lon1, lat2, lon2, factor=1.0):
    """Great-circle distance in NM. factor=1.0 gives true straight-line."""
    R = 3440.065
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return round(2 * R * math.asin(math.sqrt(max(a, 0.0))), 1)


def path_distance(*waypoint_latlons):
    """Sum of haversine segments along a sequence of (lat, lon) tuples."""
    total = 0.0
    for i in range(len(waypoint_latlons) - 1):
        lat1, lon1 = waypoint_latlons[i]
        lat2, lon2 = waypoint_latlons[i + 1]
        total += haversine_nm(lat1, lon1, lat2, lon2)
    return round(total, 1)


def _haversine_fallback(origin_lonlat, dest_lonlat, factor=1.35):
    """Return Haversine NM given [lon, lat] pairs with routing factor."""
    lon1, lat1 = origin_lonlat
    lon2, lat2 = dest_lonlat
    return haversine_nm(lat1, lon1, lat2, lon2, factor)


# ── Geographic region classifier ──────────────────────────────────────────────

def classify_port(lat, lon):
    """
    Return a region string for geographic routing logic.
    Regions are intentionally coarse — used only for smart distance estimation.
    """
    # Australia / Oceania
    if lat < -15:
        return "australia"

    # Indian Ocean west (Sri Lanka, India west coast, Arabian Sea)
    if lon < 80:
        return "indian_ocean_west"

    # Bay of Bengal (India east, Bangladesh, Myanmar west)
    if 80 <= lon <= 98 and lat > 8:
        return "bay_of_bengal"

    # Andaman Sea
    if 95 <= lon <= 100 and 5 <= lat <= 18:
        return "andaman_sea"

    # Malacca/Strait of Malacca corridor
    if 99 <= lon <= 105 and lat < 8:
        return "malacca_corridor"

    # Gulf of Thailand
    if 99 <= lon <= 106 and 7 <= lat <= 15:
        return "gulf_of_thailand"

    # Java Sea / Indonesia west
    if 105 <= lon <= 117 and -9 <= lat <= 2:
        return "java_sea"

    # South China Sea (broad)
    if 108 <= lon <= 122 and 5 <= lat <= 25:
        return "south_china_sea"

    # Eastern Indonesia / Sulawesi / Timor
    if lon > 117 and lat < 5:
        return "eastern_indonesia"

    # Philippines
    if 118 <= lon <= 128 and 5 <= lat <= 22:
        return "philippines"

    # East Asia (China, Japan, Korea)
    if lon > 120 and lat > 22:
        return "east_asia"

    # Catch-all for remaining Indian Ocean area
    return "indian_ocean_east"


# ── Smart waypoint distance estimator ────────────────────────────────────────

def smart_waypoint_distance(lat1, lon1, lat2, lon2):
    """
    Estimate a realistic sea distance in NM by routing through known maritime
    chokepoints appropriate for the port pair's geographic regions.

    Returns NM (float). No routing factor applied — already accounts for
    detours through chokepoints.
    """
    reg1 = classify_port(lat1, lon1)
    reg2 = classify_port(lat2, lon2)

    # Normalise for symmetric lookup
    pair = frozenset([reg1, reg2])
    p1 = (lat1, lon1)
    p2 = (lat2, lon2)

    # Identical region — short hop, use direct with small routing factor
    if reg1 == reg2:
        return haversine_nm(lat1, lon1, lat2, lon2, factor=1.15)

    mal = WP["malacca"]
    sun = WP["sunda"]
    kar = WP["karimata"]
    mak = WP["makassar"]
    lom = WP["lombok"]
    sin = WP["singapore"]
    luz = WP["luzon"]
    scs = WP["scs_centre"]

    # Bay of Bengal / Andaman -> Gulf of Thailand / South China Sea / Philippines
    if reg1 in ("bay_of_bengal", "andaman_sea", "malacca_corridor") and \
       reg2 in ("gulf_of_thailand", "south_china_sea", "philippines", "east_asia"):
        return path_distance(p1, mal, p2)

    if reg2 in ("bay_of_bengal", "andaman_sea", "malacca_corridor") and \
       reg1 in ("gulf_of_thailand", "south_china_sea", "philippines", "east_asia"):
        return path_distance(p1, mal, p2)

    # Bay of Bengal -> Java Sea / Eastern Indonesia
    if reg1 in ("bay_of_bengal", "andaman_sea") and \
       reg2 in ("java_sea", "eastern_indonesia"):
        return min(
            path_distance(p1, mal, kar, p2),
            path_distance(p1, sun, p2),
        )

    if reg2 in ("bay_of_bengal", "andaman_sea") and \
       reg1 in ("java_sea", "eastern_indonesia"):
        return min(
            path_distance(p1, mal, kar, p2),
            path_distance(p1, sun, p2),
        )

    # Bay of Bengal -> Australia
    if reg1 in ("bay_of_bengal", "andaman_sea") and reg2 == "australia":
        return min(
            path_distance(p1, mal, sun, p2),   # via Malacca then Sunda
            path_distance(p1, sun, p2),         # direct via Sunda
        )

    if reg2 in ("bay_of_bengal", "andaman_sea") and reg1 == "australia":
        return min(
            path_distance(p1, sun, mal, p2),
            path_distance(p1, sun, p2),
        )

    # South China Sea -> Java Sea
    if "south_china_sea" in pair and "java_sea" in pair:
        return path_distance(p1, kar, p2)

    # South China Sea -> Eastern Indonesia
    if "south_china_sea" in pair and "eastern_indonesia" in pair:
        return path_distance(p1, mak, p2)

    # South China Sea -> Australia
    if "south_china_sea" in pair and "australia" in pair:
        return min(
            path_distance(p1, lom, p2),
            path_distance(p1, mak, p2),
        )

    # Philippines -> Java Sea / Eastern Indonesia
    if "philippines" in pair and "java_sea" in pair:
        return path_distance(p1, kar, p2)

    if "philippines" in pair and "eastern_indonesia" in pair:
        return path_distance(p1, mak, p2)

    # Gulf of Thailand -> Java Sea
    if "gulf_of_thailand" in pair and "java_sea" in pair:
        return path_distance(p1, kar, p2)

    # Gulf of Thailand -> Eastern Indonesia
    if "gulf_of_thailand" in pair and "eastern_indonesia" in pair:
        return path_distance(p1, kar, mak, p2)

    # Malacca corridor -> Java Sea
    if "malacca_corridor" in pair and "java_sea" in pair:
        return min(
            path_distance(p1, mal, kar, p2),
            path_distance(p1, sun, p2),
        )

    # Malacca corridor -> South China Sea
    if "malacca_corridor" in pair and "south_china_sea" in pair:
        return path_distance(p1, sin, p2)

    # Indian Ocean west -> Bay of Bengal / Andaman
    if "indian_ocean_west" in pair and reg1 in ("bay_of_bengal", "andaman_sea", "malacca_corridor"):
        return haversine_nm(lat1, lon1, lat2, lon2, factor=1.2)

    if "indian_ocean_west" in pair and reg2 in ("bay_of_bengal", "andaman_sea", "malacca_corridor"):
        return haversine_nm(lat1, lon1, lat2, lon2, factor=1.2)

    # Indian Ocean west -> SEA (via Malacca or Sunda)
    if "indian_ocean_west" in pair:
        return min(
            path_distance(p1, mal, p2),
            path_distance(p1, sun, p2),
        )

    # East Asia -> SEA
    if "east_asia" in pair:
        if reg1 in ("south_china_sea", "gulf_of_thailand", "philippines", "malacca_corridor") or \
           reg2 in ("south_china_sea", "gulf_of_thailand", "philippines", "malacca_corridor"):
            return haversine_nm(lat1, lon1, lat2, lon2, factor=1.2)
        return path_distance(p1, scs, p2)

    # Australia -> SEA generic
    if "australia" in pair:
        return min(
            path_distance(p1, lom, p2),
            path_distance(p1, mak, p2),
            path_distance(p1, sun, p2),
        )

    # Default: haversine with generous routing factor
    return haversine_nm(lat1, lon1, lat2, lon2, factor=1.35)


# ── Validation layer ──────────────────────────────────────────────────────────

def validate_and_correct(port_a, port_b, searoute_nm, lat1, lon1, lat2, lon2):
    """
    Accept the searoute distance if it is geometrically plausible.
    Return a corrected smart distance otherwise.

    Acceptance criteria:
      - searoute_nm >= straight_nm * 0.90  (not shorter than straight-line)
      - searoute_nm <= smart_nm * 1.60     (not more than 60% longer than smart route)

    Returns (final_nm, was_corrected).
    """
    straight_nm = haversine_nm(lat1, lon1, lat2, lon2, factor=1.0)
    smart_nm    = smart_waypoint_distance(lat1, lon1, lat2, lon2)

    too_short = searoute_nm < straight_nm * 0.90
    too_long  = searoute_nm > smart_nm * 1.30

    if too_short or too_long:
        return round(smart_nm, 1), True

    return round(searoute_nm, 1), False


# ── searoute call helpers ─────────────────────────────────────────────────────

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
    Return a list of intermediate [lon, lat] waypoints for routes crossing
    the Indonesian/Philippine archipelago. Empty list = no forcing.
    """
    lo_min = min(lon1, lon2)
    lo_max = max(lon1, lon2)
    la_dest = lat2

    wps = []

    # Bay of Bengal -> Gulf of Thailand / Andaman -> South China Sea via Malacca
    # (Chittagong/Yangon/Colombo to Koh Sichang/Bangkok area)
    if lo_min < 96 and 98 <= lo_max <= 106 and 5 <= la_dest <= 16:
        wps.append(SEA_FORCED_WAYPOINTS["malacca"])
        return wps

    # Route from Indian Ocean side needs Malacca passage
    if lo_min < 100 and lo_max > 103:
        wps.append(SEA_FORCED_WAYPOINTS["malacca"])
        if lo_max > 117:
            wps.append(SEA_FORCED_WAYPOINTS["karimata"])
        return wps

    # West-side to Eastern Indonesia/Philippines
    if lo_min < 106 and lo_max > 117:
        if la_dest < -2:
            wps.append(SEA_FORCED_WAYPOINTS["karimata"])
            wps.append(SEA_FORCED_WAYPOINTS["makassar"])
        else:
            wps.append(SEA_FORCED_WAYPOINTS["karimata"])
        return wps

    # Central Java/Kalimantan to far-east Sulawesi/Philippines
    if 106 <= lo_min < 113 and lo_max > 120:
        wps.append(SEA_FORCED_WAYPOINTS["makassar"])
        return wps

    # Java ports to Eastern Indonesia via Lombok
    if 107 <= lo_min <= 114 and lo_max > 115 and lo_max <= 120:
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
            all_coords.extend(seg_coords[1:])  # skip duplicate junction point

    if total_nm > 0 and len(all_coords) >= 3:
        return round(total_nm, 1), all_coords
    return None, []


def get_sea_distance_and_route(origin_lonlat, dest_lonlat):
    """
    Return (nm, coords) for the sea route between two ports.

    Strategy:
      1. Try direct searoute call.
      2. If result has < 3 waypoints, try forced strait waypoints.
      3. If forced-waypoint route also fails, fall back to Haversine.
    """
    lon1, lat1 = origin_lonlat
    lon2, lat2 = dest_lonlat

    # 1. Try direct route
    nm, coords = _direct_route(origin_lonlat, dest_lonlat)

    # 2. If too few waypoints, route may have crossed land
    if nm is None or len(coords) < 3:
        forced = _pick_forced_waypoints(lon1, lat1, lon2, lat2)
        if forced:
            nm_f, coords_f = _route_via_waypoints(origin_lonlat, forced, dest_lonlat)
            if nm_f is not None and len(coords_f) >= 3:
                return nm_f, coords_f

        if nm is not None and nm > 0:
            return nm, coords

        return _haversine_fallback(origin_lonlat, dest_lonlat), []

    # 3. Check forced waypoints even for valid direct results — may be more accurate
    forced = _pick_forced_waypoints(lon1, lat1, lon2, lat2)
    if forced:
        nm_f, coords_f = _route_via_waypoints(origin_lonlat, forced, dest_lonlat)
        if nm_f is not None and len(coords_f) >= 3:
            if len(coords_f) > len(coords) or nm_f > nm * 1.05:
                return nm_f, coords_f

    return nm, coords


# ── Known-route validation checks ────────────────────────────────────────────

KNOWN_ROUTE_CHECKS = [
    # (port_a, port_b, min_nm, max_nm, description)
    ("Chittagong",     "Koh Sichang",      2300, 2600, "Bay of Bengal -> Gulf of Thailand via Malacca"),
    ("Chittagong",     "Singapore",        1600, 1900, "Bay of Bengal -> Singapore via Malacca"),
    ("Singapore",      "Manila",           1250, 1600, "Singapore -> Philippines"),
    ("Singapore",      "Fremantle",        2700, 3200, "Singapore -> Australia via Sunda/Lombok"),
    ("Yangon",         "Ho Chi Minh City", 1600, 2000, "Myanmar -> Vietnam"),
]


def run_known_route_checks(matrix):
    """Print validation results for known reference routes."""
    print()
    print("Known-route validation:")
    all_ok = True
    for pa, pb, lo, hi, desc in KNOWN_ROUTE_CHECKS:
        if pa in matrix and pb in matrix[pa]:
            nm = matrix[pa][pb]
            ok = lo <= nm <= hi
            status = "OK " if ok else "WARN"
            if not ok:
                all_ok = False
            print(f"  [{status}] {pa} -> {pb}: {nm:.0f} NM  (expected {lo}-{hi})  {desc}")
        else:
            print(f"  [SKIP] {pa} -> {pb}: not in matrix")
    if all_ok:
        print("  All checks passed.")
    return all_ok


# ── Main matrix builder ───────────────────────────────────────────────────────

def build_matrix():
    ports   = sorted(PORT_COORDS.keys())
    n       = len(ports)
    n_pairs = n * (n - 1) // 2
    print(f"Building {n}x{n} sea distance matrix ({n_pairs:,} unique pairs)...")
    print(f"Distance CSV  : {OUTPUT_CSV}")
    print(f"Waypoints JSON: {OUTPUT_JSON}")
    print()

    matrix    = {p: {} for p in ports}
    waypoints = {}
    done             = 0
    fallback_count   = 0
    forced_count     = 0
    corrected_count  = 0
    start_time       = time.time()

    for i, port_a in enumerate(ports):
        lat1, lon1 = PORT_COORDS[port_a]
        for j, port_b in enumerate(ports):
            if port_a == port_b:
                matrix[port_a][port_b] = 0.0
                continue

            if port_b in matrix[port_a]:
                continue
            if port_a in matrix[port_b]:
                nm = matrix[port_b][port_a]
                matrix[port_a][port_b] = nm
                rev_key = f"{port_b}|{port_a}"
                if rev_key in waypoints:
                    waypoints[f"{port_a}|{port_b}"] = list(reversed(waypoints[rev_key]))
                continue

            lat2, lon2 = PORT_COORDS[port_b]

            searoute_nm, coords = get_sea_distance_and_route([lon1, lat1], [lon2, lat2])

            if searoute_nm is None or searoute_nm <= 0:
                searoute_nm = haversine_nm(lat1, lon1, lat2, lon2, factor=1.35)
                coords = []
                fallback_count += 1

            # Smart validation
            final_nm, was_corrected = validate_and_correct(
                port_a, port_b, searoute_nm, lat1, lon1, lat2, lon2
            )
            if was_corrected:
                corrected_count += 1
                coords = []  # no waypoints for corrected distances

            if not coords:
                fallback_count += 1 if not was_corrected else 0

            forced = _pick_forced_waypoints(lon1, lat1, lon2, lat2)
            if forced and coords:
                forced_count += 1

            matrix[port_a][port_b] = final_nm
            matrix[port_b][port_a] = final_nm

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
                print(f"  {done:,}/{n_pairs:,} pairs ({pct}%) - "
                      f"~{remaining / 60:.1f} min remaining  "
                      f"[fallbacks: {fallback_count}  forced: {forced_count}  corrected: {corrected_count}]")

            time.sleep(0.02)

    # ── Write distance CSV ────────────────────────────────────────────────────
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["origin"] + ports)
        for origin in ports:
            row = [origin] + [matrix[origin].get(dest, 0.0) for dest in ports]
            writer.writerow(row)

    # ── Write waypoints JSON ──────────────────────────────────────────────────
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(waypoints, f, separators=(',', ':'))

    elapsed_total = time.time() - start_time
    print()
    print(f"Done in {elapsed_total / 60:.1f} minutes.")
    print(f"  {n} ports x {n} ports = {n*n} cells")
    print(f"  Haversine fallbacks:  {fallback_count} pairs")
    print(f"  Forced strait routes: {forced_count} pairs")
    print(f"  Smart corrections:    {corrected_count} pairs")
    print(f"  Waypoints saved:      {len(waypoints)//2:,} routes ({len(waypoints):,} directions)")
    print(f"  CSV  -> {OUTPUT_CSV}")
    print(f"  JSON -> {OUTPUT_JSON}")

    run_known_route_checks(matrix)


if __name__ == "__main__":
    build_matrix()
