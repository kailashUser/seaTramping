"""
Build a renderer-agnostic voyage timeline from a stored simulation programme.

The simulation stores a programme as a list of legs (db.top_programme_legs).
A renderer needs something different: an ordered sequence of timed segments the
vessel passes through, each with real sea-route geometry, so vessel position at
any day of the year can be interpolated.

One leg expands into up to four segments:

    ballast    previous discharge port -> load port   (skipped if same port)
    load       alongside at the load port
    laden      load port -> discharge port
    discharge  alongside at the discharge port

The output dict is the contract shared by the Three.js viewer and the video
renderer. Build it once, render it many ways.

    from modules.voyage_timeline import build_timeline
    tl = build_timeline(run_id=19, programme_rank=1)
"""

import json
import math
import os
import sqlite3
from datetime import date, timedelta

_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_DIR)

DB_PATH = os.path.join(_ROOT, "db", "compass_runs.db")
ROUTES_JSON = os.path.join(_ROOT, "data", "port_sea_routes.json")

# The DB stores total_days per leg but not how port time splits between the
# load call and the discharge call. Absent better data, split it evenly.
LOAD_SHARE = 0.5

_routes_cache = None


def _routes():
    global _routes_cache
    if _routes_cache is None:
        with open(ROUTES_JSON, encoding="utf-8") as f:
            _routes_cache = json.load(f)
    return _routes_cache


def _port_coords():
    import sys
    sys.path.insert(0, _ROOT)
    from data.port_coordinates import PORT_COORDS
    return PORT_COORDS


def great_circle_nm(lon1, lat1, lon2, lat2):
    r = 3440.065  # nautical miles
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def bearing(lon1, lat1, lon2, lat2):
    """Initial great-circle bearing in degrees, for vessel heading."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def _path(origin, dest, coords):
    """
    Sea-route waypoints for origin -> dest as [[lon, lat], ...].

    Falls back to a two-point straight line when the pair has no generated
    route, so the renderer always has geometry. `synthetic` marks those so the
    caller can report how much of the voyage is not a real sea path.
    """
    key = f"{origin}|{dest}"
    path = _routes().get(key)
    if path and len(path) >= 2:
        return [[float(x), float(y)] for x, y in path], False

    if origin not in coords or dest not in coords:
        return [], False
    lat1, lon1 = coords[origin]
    lat2, lon2 = coords[dest]
    return [[lon1, lat1], [lon2, lat2]], True


def _cumulative_nm(path):
    """Running distance along a path, used to keep speed constant between sparse waypoints."""
    out = [0.0]
    for i in range(1, len(path)):
        (lon1, lat1), (lon2, lat2) = path[i - 1], path[i]
        out.append(out[-1] + great_circle_nm(lon1, lat1, lon2, lat2))
    return out


def _run_field(row, name):
    """Read a column that may not exist in an un-migrated database."""
    if row is None:
        return None
    try:
        return row[name]
    except (IndexError, KeyError):
        return None


def hull_dimensions(meta):
    """
    Vessel LOA and beam in metres.

    Uses the IMO-supplied figures when present. Otherwise estimates from DWT
    using handysize bulker regressions, so the model still has sane
    proportions rather than a hardcoded hull.
    """
    loa, beam = meta.get("loa"), meta.get("beam")
    if loa and beam:
        return float(loa), float(beam), "imo"

    dwt = float(meta.get("dwt") or 0)
    if dwt <= 0:
        return 180.0, 30.0, "default"

    # Power-law fit anchored on real dry bulk carriers:
    #   25,000 DWT handysize  ~ 160 m LOA
    #   80,000 DWT panamax    ~ 229 m LOA
    # Length/beam ratio for bulkers sits around 6.3.
    est_loa = 7.05 * dwt ** 0.3083
    est_beam = est_loa / 6.3
    return round(float(loa) if loa else est_loa, 1), \
           round(float(beam) if beam else est_beam, 1), "estimated"


def latest_run_id(db_path=DB_PATH):
    """
    Most recent run that actually stored programme legs.

    A run row is written before its legs, so ordering by run_id alone can point
    at a run with nothing to animate. Returns None when the DB holds no usable
    run - the caller should tell the user to run a simulation first.
    """
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            """SELECT r.run_id
               FROM simulation_runs r
               JOIN top_programme_legs l ON l.run_id = r.run_id
               GROUP BY r.run_id
               ORDER BY r.run_id DESC
               LIMIT 1"""
        ).fetchone()
    finally:
        conn.close()
    return row[0] if row else None


def missing_coordinates(run_id, programme_rank=1, db_path=DB_PATH):
    """
    Ports in this programme that have no lat/lon.

    These cannot be placed, so their port calls are dropped and the vessel
    appears to skip a berth. Surface this rather than letting it pass silently.
    """
    coords = _port_coords()
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """SELECT DISTINCT origin_port, dest_port FROM top_programme_legs
               WHERE run_id = ? AND programme_rank = ?""",
            (run_id, programme_rank),
        ).fetchall()
    finally:
        conn.close()

    ports = {p for pair in rows for p in pair if p}
    return sorted(p for p in ports if p not in coords)


def build_timeline(run_id=None, programme_rank=1, start_date=None, db_path=DB_PATH):
    """
    Expand a stored programme into an ordered list of timed segments.

    `run_id=None` selects the most recent run holding programme legs, so the
    viewer always reflects the latest simulation.
    """
    if run_id is None:
        run_id = latest_run_id(db_path)
        if run_id is None:
            raise ValueError(
                "No simulation runs with stored programmes. Run a simulation first."
            )
    coords = _port_coords()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        run = conn.execute(
            "SELECT * FROM simulation_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        legs = conn.execute(
            """SELECT * FROM top_programme_legs
               WHERE run_id = ? AND programme_rank = ?
               ORDER BY voyage_num""",
            (run_id, programme_rank),
        ).fetchall()
    finally:
        conn.close()

    if not legs:
        raise ValueError(f"No legs for run_id={run_id}, programme_rank={programme_rank}")

    start_date = start_date or date(2024, 1, 1)
    segments = []
    voyages = []
    day = 0.0
    cum_profit = 0.0
    prev_port = None
    synthetic_nm = 0.0
    total_nm = 0.0

    def add_transit(kind, origin, dest, days):
        nonlocal day, synthetic_nm, total_nm
        path, synthetic = _path(origin, dest, coords)
        if len(path) < 2 or days <= 0:
            return
        cum = _cumulative_nm(path)
        total_nm += cum[-1]
        if synthetic:
            synthetic_nm += cum[-1]
        segments.append({
            "type": kind,
            "from": origin,
            "to": dest,
            "start_day": round(day, 4),
            "end_day": round(day + days, 4),
            "days": round(days, 4),
            "nm": round(cum[-1], 1),
            "path": [[round(x, 5), round(y, 5)] for x, y in path],
            "cum_nm": [round(c, 2) for c in cum],
            "synthetic": synthetic,
        })
        day += days

    def add_port_call(mode, port, days, leg):
        nonlocal day
        if port not in coords:
            return
        lat, lon = coords[port]
        segments.append({
            "type": "port",
            "mode": mode,
            "port": port,
            "lat": lat,
            "lon": lon,
            "start_day": round(day, 4),
            "end_day": round(day + days, 4),
            "days": round(days, 4),
            "commodity": leg["commodity"],
            "cargo_mt": round(leg["cargo_mt"] or 0),
        })
        day += days

    for leg in legs:
        origin, dest = leg["origin_port"], leg["dest_port"]
        laden_days = leg["laden_days"] or 0.0
        ballast_days = leg["ballast_days"] or 0.0
        port_days = max((leg["total_days"] or 0.0) - laden_days - ballast_days, 0.0)

        voyage_start = day

        if prev_port and prev_port != origin and ballast_days > 0:
            add_transit("ballast", prev_port, origin, ballast_days)

        add_port_call("load", origin, port_days * LOAD_SHARE, leg)
        add_transit("laden", origin, dest, laden_days)
        add_port_call("discharge", dest, port_days * (1 - LOAD_SHARE), leg)

        cum_profit += leg["profit_loss"] or 0.0
        voyages.append({
            "voyage_num": leg["voyage_num"],
            "origin": origin,
            "dest": dest,
            "commodity": leg["commodity"],
            "cargo_mt": round(leg["cargo_mt"] or 0),
            "freight_rate": round(leg["freight_rate"] or 0, 2),
            "gross_freight": round(leg["gross_freight"] or 0),
            "profit": round(leg["profit_loss"] or 0),
            "cum_profit": round(cum_profit),
            "start_day": round(voyage_start, 2),
            "end_day": round(day, 2),
        })
        prev_port = dest

    used_ports = sorted({s["port"] for s in segments if s["type"] == "port"})
    dropped = sorted({p for leg in legs for p in (leg["origin_port"], leg["dest_port"])
                      if p and p not in coords})

    return {
        "meta": {
            "run_id": run_id,
            "programme_rank": programme_rank,
            "vessel_name": (run["vessel_name"] if run else "") or "SEA Tramping Vessel",
            "vessel_imo": _run_field(run, "vessel_imo") or "",
            "dwt": run["dwt"] if run else None,
            "speed_laden": run["speed_laden"] if run else None,
            "speed_ballast": run["speed_ballast"] if run else None,
            # Real hull particulars when the IMO lookup supplied them. The
            # renderer scales the vessel from LOA/beam and falls back to a
            # DWT-derived estimate when they are absent.
            "loa": _run_field(run, "loa"),
            "beam": _run_field(run, "beam"),
            "vessel_type": _run_field(run, "vessel_type") or "",
            "year_built": _run_field(run, "year_built") or "",
            "flag": _run_field(run, "flag") or "",
            "start_date": start_date.isoformat(),
            "end_date": (start_date + timedelta(days=day)).isoformat(),
            "total_days": round(day, 2),
            "total_profit": round(cum_profit),
            "n_voyages": len(voyages),
            "n_ports": len(used_ports),
            "total_nm": round(total_nm, 1),
            # Share of distance drawn as a straight line because the port pair
            # has no generated sea route. Should be 0 after a route rebuild.
            "synthetic_nm": round(synthetic_nm, 1),
            "synthetic_pct": round(100 * synthetic_nm / total_nm, 1) if total_nm else 0.0,
            # Ports with no lat/lon: their calls are absent from `segments`.
            "dropped_ports": dropped,
        },
        "ports": {p: {"lat": coords[p][0], "lon": coords[p][1]} for p in used_ports if p in coords},
        "segments": segments,
        "voyages": voyages,
    }


def position_at(timeline, day):
    """
    Vessel state at a given day: lon, lat, heading and status.

    Interpolates by cumulative distance so the vessel holds a constant speed
    between sparse waypoints instead of jumping.
    """
    segs = timeline["segments"]
    if not segs:
        return None

    seg = None
    for s in segs:
        if s["start_day"] <= day <= s["end_day"]:
            seg = s
            break
    if seg is None:
        seg = segs[0] if day < segs[0]["start_day"] else segs[-1]

    if seg["type"] == "port":
        return {
            "lon": seg["lon"], "lat": seg["lat"], "heading": 0.0,
            "status": seg["mode"], "port": seg["port"],
            "commodity": seg["commodity"], "cargo_mt": seg["cargo_mt"],
        }

    span = max(seg["end_day"] - seg["start_day"], 1e-9)
    frac = min(max((day - seg["start_day"]) / span, 0.0), 1.0)
    target = frac * seg["cum_nm"][-1]

    cum, path = seg["cum_nm"], seg["path"]
    i = 1
    while i < len(cum) - 1 and cum[i] < target:
        i += 1

    seg_len = max(cum[i] - cum[i - 1], 1e-9)
    t = min(max((target - cum[i - 1]) / seg_len, 0.0), 1.0)
    (lon1, lat1), (lon2, lat2) = path[i - 1], path[i]

    return {
        "lon": lon1 + (lon2 - lon1) * t,
        "lat": lat1 + (lat2 - lat1) * t,
        "heading": bearing(lon1, lat1, lon2, lat2),
        "status": seg["type"],
        "from": seg["from"],
        "to": seg["to"],
    }


if __name__ == "__main__":
    import sys
    rid = int(sys.argv[1]) if len(sys.argv) > 1 else 19
    rank = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    tl = build_timeline(rid, rank)
    m = tl["meta"]
    print(json.dumps(m, indent=2))
    print(f"segments: {len(tl['segments'])}  ports: {len(tl['ports'])}")
    for d in (0, 30, 90, 180, 300):
        print(f"  day {d:>3}: {position_at(tl, d)}")
