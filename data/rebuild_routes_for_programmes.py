"""
Scoped rebuild of port_sea_routes.json for the ports actually used by stored
simulation programmes.

The full build_distance_matrix.py covers all 407 ports in PORT_COORDS
(82,621 pairs, several hours). The route file currently on disk was built when
PORT_COORDS held ~115 ports, so every port added since - notably the Vietnamese
cluster (Cai Mep, Ho Chi Minh City, Campha, Son Duong, ...) - has no waypoints
at all, and the voyage animation has no geometry to follow.

This script rebuilds only the pairs reachable from db/compass_runs.db programmes
(~68 ports, ~2,278 pairs) and MERGES them into the existing file. Existing
routes are left untouched; the original is backed up first.

    python data/rebuild_routes_for_programmes.py
"""

import json
import os
import shutil
import sqlite3
import sys
import time
from datetime import datetime
from itertools import combinations

_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_DIR)
sys.path.insert(0, _ROOT)

from data.build_distance_matrix import get_sea_distance_and_route  # noqa: E402
from data.port_coordinates import PORT_COORDS  # noqa: E402

ROUTES_JSON = os.path.join(_DIR, "port_sea_routes.json")
DB_PATH = os.path.join(_ROOT, "db", "compass_runs.db")


def ports_used_by_programmes():
    """Every port appearing as an origin or destination in any stored programme."""
    conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.execute(
            "SELECT DISTINCT origin_port, dest_port FROM top_programme_legs"
        ).fetchall()
    finally:
        conn.close()

    ports = set()
    for origin, dest in rows:
        if origin:
            ports.add(origin)
        if dest:
            ports.add(dest)
    return sorted(ports)


def main():
    ports = ports_used_by_programmes()
    known = [p for p in ports if p in PORT_COORDS]
    unknown = [p for p in ports if p not in PORT_COORDS]

    print(f"Ports referenced by stored programmes: {len(ports)}")
    print(f"  with coordinates:    {len(known)}")
    if unknown:
        print(f"  MISSING coordinates: {len(unknown)} -> {unknown}")
        print("  (these cannot be routed and will still break the animation)")

    with open(ROUTES_JSON, encoding="utf-8") as f:
        routes = json.load(f)
    print(f"\nExisting route file: {len(routes):,} directed entries")

    backup = f"{ROUTES_JSON}.bak-{datetime.now():%Y%m%d-%H%M%S}"
    shutil.copy2(ROUTES_JSON, backup)
    print(f"Backed up to: {os.path.basename(backup)}")

    pairs = list(combinations(known, 2))
    todo = [
        (a, b) for a, b in pairs
        if not routes.get(f"{a}|{b}") or not routes.get(f"{b}|{a}")
    ]
    print(f"\nPairs in scope: {len(pairs):,}   already routed: {len(pairs) - len(todo):,}   to build: {len(todo):,}\n")

    if not todo:
        print("Nothing to do.")
        return

    start = time.time()
    built = empty = 0

    for i, (port_a, port_b) in enumerate(todo, 1):
        lat1, lon1 = PORT_COORDS[port_a]
        lat2, lon2 = PORT_COORDS[port_b]

        try:
            _nm, coords = get_sea_distance_and_route((lon1, lat1), (lon2, lat2))
        except Exception as exc:  # a single bad pair must not kill the batch
            print(f"  ! {port_a} -> {port_b}: {type(exc).__name__}: {exc}")
            coords = []

        if coords:
            routes[f"{port_a}|{port_b}"] = coords
            routes[f"{port_b}|{port_a}"] = list(reversed(coords))
            built += 1
        else:
            empty += 1

        if i % 100 == 0 or i == len(todo):
            elapsed = time.time() - start
            rate = i / max(elapsed, 1e-6)
            remaining = (len(todo) - i) / max(rate, 1e-6)
            print(
                f"  {i:,}/{len(todo):,} ({i * 100 // len(todo)}%)  "
                f"built {built:,}  no-geometry {empty:,}  "
                f"~{remaining / 60:.1f} min left"
            )

    with open(ROUTES_JSON, "w", encoding="utf-8") as f:
        json.dump(routes, f, separators=(",", ":"))

    print(f"\nDone in {(time.time() - start) / 60:.1f} min.")
    print(f"  routes built:   {built:,} pairs")
    print(f"  no geometry:    {empty:,} pairs (haversine fallback, straight line)")
    print(f"  file now holds: {len(routes):,} directed entries")


if __name__ == "__main__":
    main()
