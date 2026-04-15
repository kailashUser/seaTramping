"""
Cargo Intelligence Layer for COMPASS simulation.
Source: AXS Marine trade flow analysis + Cargo Analysis data.
"""

# ── Cargo Compatibility Matrix ───────────────────────────────────────────────
# Cleaning grade: G=Good, W=Washable, S=Serious, X=Incompatible
# Cost in USD for hold cleaning required before loading new cargo
# Format: {(previous_cargo, next_cargo): {"grade": str, "days": float, "cost": int}}
# If pair not in dict, assume G (minor cleaning, $1,000)

CARGO_COMPATIBILITY = {
    # Coal → other
    ("Steam Coal",   "Bagged Sugar"):       {"grade": "S", "days": 2.0, "cost": 8000},
    ("Steam Coal",   "Fertilizers"):        {"grade": "S", "days": 2.0, "cost": 8000},
    ("Steam Coal",   "Grain"):              {"grade": "S", "days": 2.0, "cost": 8000},
    ("Steam Coal",   "Rice"):               {"grade": "S", "days": 2.0, "cost": 8000},
    ("Steam Coal",   "Nickel Ore"):         {"grade": "G", "days": 0.5, "cost": 1500},
    ("Steam Coal",   "Iron Ore"):           {"grade": "G", "days": 0.5, "cost": 1500},
    ("Steam Coal",   "Clinker"):            {"grade": "G", "days": 0.5, "cost": 1500},
    ("Steam Coal",   "Palm Kernel Expeller"): {"grade": "W", "days": 1.0, "cost": 3000},
    ("Steam Coal",   "Bauxite"):            {"grade": "G", "days": 0.5, "cost": 1500},
    ("Steam Coal",   "Gypsum"):             {"grade": "G", "days": 0.5, "cost": 1500},
    ("Steam Coal",   "Salt"):               {"grade": "S", "days": 1.5, "cost": 6000},
    ("Steam Coal",   "Limestone"):          {"grade": "G", "days": 0.5, "cost": 1500},
    ("Steam Coal",   "Aggregates"):         {"grade": "G", "days": 0.5, "cost": 1500},
    ("Steam Coal",   "Steels"):             {"grade": "G", "days": 0.5, "cost": 1500},
    ("Steam Coal",   "Scrap"):              {"grade": "G", "days": 0.5, "cost": 1500},
    # Coking Coal → other (same as steam coal)
    ("Coking Coal",  "Rice"):               {"grade": "S", "days": 2.0, "cost": 8000},
    ("Coking Coal",  "Sugar"):              {"grade": "S", "days": 2.0, "cost": 8000},
    ("Coking Coal",  "Fertilizers"):        {"grade": "S", "days": 2.0, "cost": 8000},
    # Nickel Ore → other
    ("Nickel Ore",   "Steam Coal"):         {"grade": "G", "days": 0.5, "cost": 1000},
    ("Nickel Ore",   "Bagged Sugar"):       {"grade": "S", "days": 2.0, "cost": 8000},
    ("Nickel Ore",   "Grain"):              {"grade": "S", "days": 2.0, "cost": 8000},
    ("Nickel Ore",   "Fertilizers"):        {"grade": "W", "days": 1.0, "cost": 3500},
    ("Nickel Ore",   "Rice"):               {"grade": "S", "days": 2.0, "cost": 8000},
    # Clinker → other
    ("Clinker",      "Grain"):              {"grade": "X", "days": 3.0, "cost": 15000},
    ("Clinker",      "Rice"):               {"grade": "X", "days": 3.0, "cost": 15000},
    ("Clinker",      "Bagged Sugar"):       {"grade": "X", "days": 3.0, "cost": 15000},
    ("Clinker",      "Sugar"):              {"grade": "X", "days": 3.0, "cost": 15000},
    ("Clinker",      "Steam Coal"):         {"grade": "G", "days": 0.5, "cost": 1500},
    ("Clinker",      "Fertilizers"):        {"grade": "W", "days": 1.5, "cost": 5000},
    ("Clinker",      "Palm Kernel Expeller"): {"grade": "W", "days": 1.5, "cost": 5000},
    # Sugar → other
    ("Sugar",        "Steam Coal"):         {"grade": "S", "days": 2.0, "cost": 7000},
    ("Sugar",        "Fertilizers"):        {"grade": "W", "days": 1.0, "cost": 3000},
    ("Sugar",        "Grain"):              {"grade": "G", "days": 0.5, "cost": 1000},
    ("Sugar",        "Rice"):              {"grade": "G", "days": 0.5, "cost": 1000},
    # PKE → other
    ("Palm Kernel Expeller", "Grain"):      {"grade": "W", "days": 1.0, "cost": 3000},
    ("Palm Kernel Expeller", "Rice"):       {"grade": "W", "days": 1.5, "cost": 4000},
    ("Palm Kernel Expeller", "Steam Coal"): {"grade": "G", "days": 0.5, "cost": 1500},
    ("Palm Kernel Expeller", "Fertilizers"):{"grade": "W", "days": 1.0, "cost": 3000},
    # Grain / Rice → other
    ("Rice",         "Steam Coal"):         {"grade": "S", "days": 2.0, "cost": 7000},
    ("Rice",         "Fertilizers"):        {"grade": "G", "days": 0.5, "cost": 1500},
    ("Rice",         "Grain"):              {"grade": "G", "days": 0.0, "cost": 0},
    # Fertilizers → other
    ("Fertilizers",  "Grain"):              {"grade": "G", "days": 0.5, "cost": 1500},
    ("Fertilizers",  "Rice"):              {"grade": "G", "days": 0.5, "cost": 1500},
    ("Fertilizers",  "Steam Coal"):         {"grade": "G", "days": 0.5, "cost": 1500},
    ("Fertilizers",  "Nickel Ore"):         {"grade": "G", "days": 0.5, "cost": 1500},
}


def get_cleaning_cost(prev_cargo: str, next_cargo: str) -> dict:
    """
    Return hold cleaning requirement when switching from prev_cargo to next_cargo.
    Returns {"grade": str, "days": float, "cost": int}
    """
    if not prev_cargo or prev_cargo == next_cargo:
        return {"grade": "G", "days": 0.0, "cost": 0}
    result = CARGO_COMPATIBILITY.get((prev_cargo, next_cargo))
    if result:
        return result
    result_rev = CARGO_COMPATIBILITY.get((next_cargo, prev_cargo))
    if result_rev:
        return result_rev
    # Default: minor cleaning for unknown combination
    return {"grade": "G", "days": 0.5, "cost": 1000}


# ── Backhaul Ratio by Country ────────────────────────────────────────────────
# Multiplier applied to profit score during route selection only.
# Does NOT change actual P&L — affects which routes the algorithm prefers.
# 1.0 = no penalty, <1.0 = algorithm de-weights weak backhaul destinations.

BACKHAUL_PENALTY_MULTIPLIER = {
    "Philippines":  0.88,   # Very weak backhaul — almost always ballast return
    "Bangladesh":   0.92,   # Mostly import-dominated, limited return cargo
    "Myanmar":      0.90,   # Very weak backhaul
    "Cambodia":     0.95,   # Minimal cargo both ways
    "Timor-Leste":  0.95,   # Almost no return cargo
}


def get_backhaul_penalty(discharge_country: str) -> float:
    """
    Return profit score multiplier for route selection (0.85–1.0).
    Applied to scoring only — does not change actual voyage P&L.
    """
    return BACKHAUL_PENALTY_MULTIPLIER.get(discharge_country, 1.0)


# ── Seasonal Freight Rate Factors ────────────────────────────────────────────
# Source: AXS Marine 5-year cargo analysis
# Factor applied to base freight rate by month (1=Jan, 12=Dec)
# > 1.0 = peak season, < 1.0 = off-season

SEASONAL_FACTORS = {
    "Steam Coal": {
        1: 1.05, 2: 1.08, 3: 1.15, 4: 1.12, 5: 1.10, 6: 0.95,
        7: 0.88, 8: 0.85, 9: 0.90, 10: 1.02, 11: 1.10, 12: 1.15,
    },
    "Coking Coal": {
        1: 1.05, 2: 1.08, 3: 1.15, 4: 1.12, 5: 1.10, 6: 0.95,
        7: 0.88, 8: 0.85, 9: 0.90, 10: 1.02, 11: 1.10, 12: 1.15,
    },
    "Nickel Ore": {
        1: 0.95, 2: 0.98, 3: 1.00, 4: 1.10, 5: 1.12, 6: 1.08,
        7: 1.05, 8: 1.00, 9: 0.95, 10: 0.90, 11: 0.88, 12: 0.92,
    },
    "Clinker": {
        1: 0.95, 2: 1.00, 3: 1.08, 4: 1.12, 5: 1.15, 6: 1.10,
        7: 1.05, 8: 1.00, 9: 1.02, 10: 1.05, 11: 1.08, 12: 0.98,
    },
    "Sugar": {
        1: 1.15, 2: 1.18, 3: 1.20, 4: 1.15, 5: 1.05, 6: 0.90,
        7: 0.85, 8: 0.88, 9: 0.90, 10: 0.95, 11: 1.00, 12: 1.10,
    },
    "Palm Kernel Expeller": {
        1: 1.05, 2: 1.08, 3: 1.05, 4: 0.95, 5: 0.90, 6: 0.88,
        7: 0.85, 8: 0.90, 9: 0.95, 10: 1.00, 11: 1.05, 12: 1.08,
    },
    "Rice": {
        1: 1.05, 2: 1.08, 3: 1.12, 4: 1.10, 5: 1.05, 6: 0.95,
        7: 0.90, 8: 0.88, 9: 0.92, 10: 1.00, 11: 1.05, 12: 1.08,
    },
}

_NEUTRAL = {m: 1.0 for m in range(1, 13)}


def get_seasonal_factor(commodity: str, month: int) -> float:
    """
    Return seasonal freight rate multiplier for commodity in given month (1–12).
    Returns 1.0 for unknown commodities.
    """
    return SEASONAL_FACTORS.get(commodity, _NEUTRAL).get(month, 1.0)
