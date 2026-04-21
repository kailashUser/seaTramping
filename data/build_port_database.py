"""
COMPASS Port Database Builder
==============================
One-time script that reads your Excel files and builds:
  - data/port_coordinates.py   (lat/lon for every port)
  - data/port_restrictions.py  (draft limits, suitability for every port)

Run once:  python data/build_port_database.py
Takes approximately 10-15 minutes (API rate limiting).
After running, the generated files replace the existing ones.

Sources:
  - Port names + suitability: SEA_Port_Restrictions_20KDWT.xlsx
  - All port names from trade: D1_Port_Pair_Matrix_Advantis.xlsx
  - Coordinates: OpenStreetMap Nominatim API (free, no key required)
"""

import os
import re
import time
import json
import requests
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# ─── STEP A: Load port restrictions from Excel ────────────────────────────────

def load_port_restrictions():
    """
    Read SEA_Port_Restrictions_20KDWT.xlsx.
    Returns dict: {port_name: {country, max_draft, max_loa, suitability, notes}}
    """
    path = os.path.join(BASE_DIR, "SEA_Port_Restrictions_20KDWT.xlsx")
    df   = pd.read_excel(path, header=1)

    restrictions = {}
    for _, row in df.iterrows():
        port = str(row.get("Port", "")).strip()
        if not port or "ports)" in port or port == "nan":
            continue

        country   = str(row.get("Country", "")).strip()
        max_draft = row.get("Max Draft (m)", None)
        max_loa   = row.get("Max LOA (m)", None)
        suit_raw  = str(row.get("Suitability (20K DWT)", "")).strip()
        notes     = str(row.get("Notes", "")).strip()
        primary   = str(row.get("Primary Cargo", "")).strip()

        suit_upper = suit_raw.upper()
        if "NOT SUITABLE" in suit_upper or "NOT_SUITABLE" in suit_upper:
            status = "NOT_SUITABLE"
        elif "RESTRICTED" in suit_upper:
            status = "RESTRICTED"
        elif "EXCELLENT" in suit_upper:
            status = "EXCELLENT"
        elif "GOOD" in suit_upper:
            status = "GOOD"
        else:
            status = "EXCELLENT"

        restrictions[port] = {
            "country":   country,
            "max_draft": float(max_draft) if pd.notna(max_draft) else 14.0,
            "max_loa":   float(max_loa)   if pd.notna(max_loa)   else None,
            "status":    status,
            "notes":     notes   if notes   != "nan" else "",
            "primary":   primary if primary != "nan" else "",
        }

    print(f"✓ Loaded {len(restrictions)} ports from SEA_Port_Restrictions_20KDWT.xlsx")
    return restrictions


# ─── STEP B: Load all unique ports from D1 matrix ────────────────────────────

def load_all_d1_ports():
    """
    Read D1_Port_Pair_Matrix_Advantis.xlsx.
    Returns dict: {port_name: country}
    """
    path = os.path.join(BASE_DIR, "D1_Port_Pair_Matrix_Advantis.xlsx")
    df   = pd.read_excel(path, header=5)
    df.columns = [
        "row_num", "origin_country", "origin_port",
        "dest_country", "dest_port",
        "commodity", "category",
        "vol_2020", "vol_2021", "vol_2022", "vol_2023", "vol_2024",
        "total_vol", "years_active", "direction",
    ]

    ports = {}
    for _, row in df.iterrows():
        for port, country in [
            (row["origin_port"], row["origin_country"]),
            (row["dest_port"],   row["dest_country"]),
        ]:
            if pd.notna(port) and pd.notna(country):
                ports[str(port).strip()] = str(country).strip()

    print(f"✓ Loaded {len(ports)} unique ports from D1 matrix")
    return ports


# ─── STEP C: Load port volumes for filtering Far East ports ──────────────────

def load_port_volumes():
    path = os.path.join(BASE_DIR, "D1_Port_Pair_Matrix_Advantis.xlsx")
    df   = pd.read_excel(path, header=5)
    df.columns = [
        "row_num", "origin_country", "origin_port",
        "dest_country", "dest_port",
        "commodity", "category",
        "vol_2020", "vol_2021", "vol_2022", "vol_2023", "vol_2024",
        "total_vol", "years_active", "direction",
    ]
    vols = {}
    for _, row in df.iterrows():
        for port in [row["origin_port"], row["dest_port"]]:
            if pd.notna(port):
                p = str(port).strip()
                vols[p] = vols.get(p, 0) + (row["total_vol"] or 0)
    return vols


# ─── STEP D: Fetch coordinates from OpenStreetMap Nominatim ──────────────────

CACHE_FILE = os.path.join(BASE_DIR, "_coord_cache.json")


def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE) as f:
            return json.load(f)
    return {}


def save_cache(cache):
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)


def fetch_coords(port_name: str, country: str, cache: dict) -> tuple:
    """
    Get (lat, lon) for a port using OpenStreetMap Nominatim.
    Returns (lat, lon) tuple or None if not found.
    Uses cache to avoid re-fetching.
    """
    cache_key = f"{port_name}|{country}"
    if cache_key in cache:
        return tuple(cache[cache_key]) if cache[cache_key] else None

    headers = {"User-Agent": "COMPASS-Maritime-Simulation/1.0"}

    queries = [
        f"{port_name} port {country}",
        f"{port_name} harbour {country}",
        f"{port_name} {country}",
        port_name,
    ]

    for query in queries:
        try:
            resp = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": query, "format": "json", "limit": 1,
                        "featuretype": "settlement"},
                headers=headers,
                timeout=10,
            )
            results = resp.json()
            if results:
                lat = round(float(results[0]["lat"]), 4)
                lon = round(float(results[0]["lon"]), 4)
                cache[cache_key] = [lat, lon]
                save_cache(cache)
                time.sleep(1.1)
                return (lat, lon)
        except Exception as e:
            print(f"  ⚠ API error for '{query}': {e}")
            time.sleep(2)

    cache[cache_key] = None
    save_cache(cache)
    time.sleep(1.1)
    return None


# ─── STEP E: Scope — which ports to include ──────────────────────────────────

SEA_LOAD_COUNTRIES = {
    "Indonesia", "Philippines", "Vietnam", "Malaysia", "Thailand",
    "Singapore", "Bangladesh", "Myanmar", "Cambodia", "Timor-Leste",
    "Brunei", "Sri Lanka",
}

FAR_EAST_DISCHARGE_COUNTRIES = {
    "China", "Japan", "Korea South",
    "Taiwan, Province of China", "Hong Kong",
}

FAR_EAST_MIN_VOLUME = 5_000_000


# ─── STEP F: Build port_coordinates.py ───────────────────────────────────────

def build_coordinates_file(all_d1_ports, port_restrictions, port_volumes):
    """Build port_coordinates.py by fetching coords for all needed ports."""

    # Load existing coordinates (keep what we already have)
    existing_coords = {}
    coords_path = os.path.join(BASE_DIR, "port_coordinates.py")
    if os.path.exists(coords_path):
        with open(coords_path, encoding="utf-8") as f:
            content = f.read()
        matches = re.findall(
            r'"([^"]+)":\s*\((-?\d+\.\d+),\s*(-?\d+\.\d+)\)',
            content
        )
        for name, lat, lon in matches:
            existing_coords[name] = (float(lat), float(lon))
        print(f"✓ Loaded {len(existing_coords)} existing coordinates")

    # Determine which ports we need
    needed_ports = {}

    for port, country in all_d1_ports.items():
        if country in SEA_LOAD_COUNTRIES:
            needed_ports[port] = country

    for port, country in all_d1_ports.items():
        if country in FAR_EAST_DISCHARGE_COUNTRIES:
            vol = port_volumes.get(port, 0)
            if vol >= FAR_EAST_MIN_VOLUME:
                needed_ports[port] = country

    print(f"\n→ Ports needed: {len(needed_ports)}")
    already = sum(1 for p in needed_ports if p in existing_coords)
    print(f"  Already have coords: {already}")
    missing = {p: c for p, c in needed_ports.items() if p not in existing_coords}
    print(f"  Need to fetch coords: {len(missing)}")

    cache = load_cache()
    all_coords = dict(existing_coords)
    not_found  = []

    for i, (port, country) in enumerate(missing.items(), 1):
        print(f"  [{i}/{len(missing)}] Fetching: {port} ({country})...", end=" ", flush=True)
        coords = fetch_coords(port, country, cache)
        if coords:
            all_coords[port] = coords
            print(f"✓ {coords}")
        else:
            not_found.append(port)
            print("✗ not found")

    # Group by region for output
    sea_by_country = {}
    fe_by_country  = {}
    for port, country in needed_ports.items():
        if port not in all_coords:
            continue
        if country in FAR_EAST_DISCHARGE_COUNTRIES:
            fe_by_country.setdefault(country, []).append((port, all_coords[port]))
        else:
            sea_by_country.setdefault(country, []).append((port, all_coords[port]))

    sea_count = sum(len(v) for v in sea_by_country.values())
    fe_count  = sum(len(v) for v in fe_by_country.values())

    lines = [
        '"""',
        'COMPASS Port Coordinates Database',
        'AUTO-GENERATED by data/build_port_database.py',
        'Do not edit manually — re-run the build script to update.',
        f'SEA ports: {sea_count} | Far East ports: {fe_count}',
        '"""',
        '',
        'PORT_COORDS = {',
    ]

    for country in sorted(sea_by_country.keys()):
        lines.append(f'    # ── {country.upper()} ──────────────────────────────')
        for port, (lat, lon) in sorted(sea_by_country[country]):
            lines.append(f'    "{port}": ({lat}, {lon}),')
        lines.append('')

    lines.append('    # ═══ FAR EAST DISCHARGE PORTS ═══════════════════════')
    for country in sorted(fe_by_country.keys()):
        lines.append(f'    # ── {country.upper()} ──────────────────────────────')
        for port, (lat, lon) in sorted(fe_by_country[country]):
            lines.append(f'    "{port}": ({lat}, {lon}),')
        lines.append('')

    lines.append('}')

    with open(coords_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\n✓ Written {sea_count + fe_count} ports to port_coordinates.py")

    if not_found:
        print(f"\n⚠ Could not find coordinates for {len(not_found)} ports:")
        for p in not_found:
            print(f"  - {p}")
        print("  These ports will be excluded from the simulation.")

    return all_coords


# ─── STEP G: Build port_restrictions.py ──────────────────────────────────────

def build_restrictions_file(all_d1_ports, port_restrictions,
                             all_coords, port_volumes):
    """Build port_restrictions.py from Excel data."""

    port_status = {}

    for port in all_coords:
        country = all_d1_ports.get(port, "")

        if port in port_restrictions:
            r = port_restrictions[port]
            port_status[port] = {
                "status":    r["status"],
                "max_draft": r["max_draft"],
                "max_loa":   r["max_loa"],
                "notes":     r["notes"],
                "country":   r["country"] or country,
            }
        elif country in FAR_EAST_DISCHARGE_COUNTRIES:
            port_status[port] = {
                "status":    "EXCELLENT",
                "max_draft": 14.0,
                "max_loa":   None,
                "notes":     f"{country} bulk discharge port",
                "country":   country,
            }
        else:
            port_status[port] = {
                "status":    "GOOD",
                "max_draft": 10.0,
                "max_loa":   None,
                "notes":     "Default — not in restriction database",
                "country":   country,
            }

    restr_path = os.path.join(BASE_DIR, "port_restrictions.py")

    lines = [
        '"""',
        'COMPASS Port Restrictions Database',
        'AUTO-GENERATED by data/build_port_database.py',
        'Do not edit manually — re-run the build script to update.',
        f'Total ports: {len(port_status)}',
        '"""',
        '',
        'PORT_SUITABILITY = {',
    ]

    for port in sorted(port_status.keys()):
        r = port_status[port]
        loa_str = str(r["max_loa"]) if r["max_loa"] else "None"
        notes   = r["notes"].replace('"', "'")
        lines.append(
            f'    "{port}": {{"status": "{r["status"]}", '
            f'"max_draft": {r["max_draft"]}, '
            f'"max_loa": {loa_str}, '
            f'"notes": "{notes}"}},'
        )

    lines += [
        '}',
        '',
        '# Derived sets used by simulation_engine.py',
        'NOT_SUITABLE_PORTS = {',
        '    p for p, v in PORT_SUITABILITY.items()',
        '    if v["status"] == "NOT_SUITABLE"',
        '}',
        '',
        'RESTRICTED_PORTS = {',
        '    p: v for p, v in PORT_SUITABILITY.items()',
        '    if v["status"] == "RESTRICTED"',
        '}',
        '',
        'TIDAL_PENALTY_DAYS = {',
        '    "Samarinda":             0.5,',
        '    "Bangkok (Khlong Toei)": 1.5,',
        '    "Mongla":                1.0,',
        '    "Yangon":                1.0,',
        '    "Songkhla":              0.5,',
        '    "Dili":                  0.5,',
        '    "Gresik":                0.5,',
        '    "Padang":                0.5,',
        '    "Tarakan Island":        0.5,',
        '}',
        '',
        'DISCHARGE_BLOCKED_PORTS = {',
        '    "Bangkok (Khlong Toei)": 8.2,',
        '    "Meulaboh":              8.0,',
        '    "Gresik":                9.0,',
        '    "Padang":                9.0,',
        '    "Samarinda":             7.0,',
        '    "Mongla":                7.5,',
        '    "Yangon":                9.1,',
        '    "Songkhla":              8.0,',
        '    "Dili":                  8.0,',
        '    "Tarakan Island":        8.0,',
        '}',
        '',
        '',
        'def get_port_status(port_name: str) -> str:',
        '    return PORT_SUITABILITY.get(port_name, {}).get("status", "GOOD")',
        '',
        '',
        'def is_port_blocked(port_name: str) -> bool:',
        '    return port_name in NOT_SUITABLE_PORTS',
        '',
        '',
        'def is_port_restricted(port_name: str) -> bool:',
        '    return port_name in RESTRICTED_PORTS',
        '',
        '',
        'def get_tidal_penalty(port_name: str) -> float:',
        '    return TIDAL_PENALTY_DAYS.get(port_name, 0.0)',
        '',
        '',
        'def validate_port_for_vessel(',
        '        port_name: str,',
        '        laden_draft: float = 9.5,',
        '        ballast_draft: float = 5.5,',
        '        loa: float = 150.0) -> dict:',
        '    info = PORT_SUITABILITY.get(port_name, {',
        '        "status": "GOOD", "max_draft": 14.0,',
        '        "max_loa": None, "notes": "Unknown port"',
        '    })',
        '    max_draft = info.get("max_draft", 14.0)',
        '    max_loa   = info.get("max_loa")',
        '    status    = info.get("status", "GOOD")',
        '    loa_ok      = (max_loa is None) or (loa <= max_loa)',
        '    can_laden   = (laden_draft   <= max_draft) and loa_ok and (status != "NOT_SUITABLE")',
        '    can_ballast = (ballast_draft <= max_draft) and loa_ok and (status != "NOT_SUITABLE")',
        '    return {',
        '        "can_call_laden":   can_laden,',
        '        "can_call_ballast": can_ballast,',
        '        "status":           status,',
        '        "max_draft":        max_draft,',
        '        "tidal_penalty":    get_tidal_penalty(port_name),',
        '        "notes":            info.get("notes", ""),',
        '    }',
    ]

    with open(restr_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    counts = {}
    for r in port_status.values():
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print(f"\n✓ Written {len(port_status)} ports to port_restrictions.py")
    for status, count in sorted(counts.items()):
        print(f"  {status}: {count}")

    return port_status


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("COMPASS Port Database Builder")
    print("=" * 60)

    print("\n[1/5] Loading port restrictions from Excel...")
    port_restrictions = load_port_restrictions()

    print("\n[2/5] Loading all ports from D1 matrix...")
    all_d1_ports = load_all_d1_ports()

    print("\n[3/5] Loading port volumes...")
    port_volumes = load_port_volumes()

    print("\n[4/5] Building coordinates file (fetching from OpenStreetMap)...")
    print("      This takes ~10-15 minutes. Progress saved — safe to interrupt.")
    all_coords = build_coordinates_file(all_d1_ports, port_restrictions, port_volumes)

    print("\n[5/5] Building restrictions file...")
    build_restrictions_file(all_d1_ports, port_restrictions, all_coords, port_volumes)

    if os.path.exists(CACHE_FILE):
        os.remove(CACHE_FILE)

    print("\n" + "=" * 60)
    print("✓ COMPLETE — Port database built successfully")
    print("  Files updated:")
    print("    data/port_coordinates.py")
    print("    data/port_restrictions.py")
    print()
    print("  Next step: python data/build_distance_matrix.py")
    print("  (Rebuild sea distance matrix with new ports)")
    print("=" * 60)


if __name__ == "__main__":
    main()
