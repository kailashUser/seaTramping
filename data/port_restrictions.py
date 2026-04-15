# Port Restrictions for 20K DWT Handysize Bulk Carrier
# Source: SEA_Complete_Port_Restrictions data
# Vessel: Draft 9.5m laden / 5.5m ballast / LOA 150m / Beam 24m
# ============================================================

# Suitability ratings:
# EXCELLENT    — fully accessible at all times, no restrictions
# GOOD         — accessible with standard precautions
# RESTRICTED   — conditional access (tidal, draft limits, reduced cargo)
# NOT_SUITABLE — vessel cannot enter under any condition

PORT_SUITABILITY = {
    # Indonesia — EXCELLENT
    "Taboneo - Banjarmasin":    {"status": "EXCELLENT",    "max_draft": 14.0, "max_loa": None, "notes": "Major coal loading terminal"},
    "Muara Berau":              {"status": "EXCELLENT",    "max_draft": 13.0, "max_loa": None, "notes": "Offshore coal terminal"},
    "Balikpapan":               {"status": "EXCELLENT",    "max_draft": 14.0, "max_loa": None, "notes": "Multi-cargo port"},
    "Tanjung Bara CT":          {"status": "EXCELLENT",    "max_draft": 14.0, "max_loa": None, "notes": "Coal terminal"},
    "Muara Pantai":             {"status": "EXCELLENT",    "max_draft": 13.0, "max_loa": None, "notes": "Coal loading"},
    "Bunati":                   {"status": "EXCELLENT",    "max_draft": 13.0, "max_loa": None, "notes": "Coal terminal"},
    "Adang Bay":                {"status": "EXCELLENT",    "max_draft": 13.0, "max_loa": None, "notes": "Coal loading"},
    "Bahudopi":                 {"status": "EXCELLENT",    "max_draft": 12.0, "max_loa": None, "notes": "Nickel ore terminal"},
    "Tanjung Pemancingan":      {"status": "EXCELLENT",    "max_draft": 13.0, "max_loa": None, "notes": "Coal loading"},
    "Bontang":                  {"status": "EXCELLENT",    "max_draft": 12.0, "max_loa": None, "notes": "LNG + coal"},
    "Muara Satui":              {"status": "EXCELLENT",    "max_draft": 13.0, "max_loa": None, "notes": "Coal terminal"},
    "Sangkulirang":             {"status": "EXCELLENT",    "max_draft": 13.0, "max_loa": None, "notes": "Coal loading"},
    "Cigading":                 {"status": "EXCELLENT",    "max_draft": 14.0, "max_loa": None, "notes": "Multi-cargo"},
    "Jakarta (Tanjung Priok)":  {"status": "EXCELLENT",    "max_draft": 14.0, "max_loa": None, "notes": "Main container/bulk port"},
    "Kaliorang":                {"status": "EXCELLENT",    "max_draft": 13.0, "max_loa": None, "notes": "Coal terminal"},
    "Senipah Terminal":         {"status": "EXCELLENT",    "max_draft": 13.0, "max_loa": None, "notes": "Oil/cargo terminal"},
    "Tarahan":                  {"status": "EXCELLENT",    "max_draft": 14.0, "max_loa": None, "notes": "Coal discharge"},
    "Asam Asam":                {"status": "EXCELLENT",    "max_draft": 13.0, "max_loa": None, "notes": "Coal terminal"},
    "Weda Bay":                 {"status": "EXCELLENT",    "max_draft": 12.0, "max_loa": None, "notes": "Nickel ore"},
    "Pulau Laut":               {"status": "EXCELLENT",    "max_draft": 13.0, "max_loa": None, "notes": "Coal terminal"},
    "Surabaya":                 {"status": "EXCELLENT",    "max_draft": 10.0, "max_loa": None, "notes": "Major Java port"},
    "Semarang":                 {"status": "EXCELLENT",    "max_draft": 10.0, "max_loa": None, "notes": "Central Java port"},
    "Paiton":                   {"status": "EXCELLENT",    "max_draft": 12.0, "max_loa": None, "notes": "Coal discharge - power plant"},
    "Tanjung Jati":             {"status": "EXCELLENT",    "max_draft": 14.0, "max_loa": None, "notes": "Coal discharge"},
    "Celukan Bawang":           {"status": "EXCELLENT",    "max_draft": 12.0, "max_loa": None, "notes": "Coal discharge Bali"},
    "Tanjung Intan (Cilacap)":  {"status": "EXCELLENT",    "max_draft": 11.0, "max_loa": None, "notes": "South Java bulk port"},
    "Palembang":                {"status": "GOOD",         "max_draft": 10.0, "max_loa": None, "notes": "River port, reduced draft"},
    "Teluk Bayur (Padang)":     {"status": "GOOD",         "max_draft": 10.0, "max_loa": None, "notes": "West Sumatra port"},
    "Belawan (Medan)":          {"status": "EXCELLENT",    "max_draft": 11.0, "max_loa": None, "notes": "North Sumatra main port"},
    "Panjang (Lampung)":        {"status": "EXCELLENT",    "max_draft": 11.0, "max_loa": None, "notes": "South Sumatra port"},
    # Indonesia — RESTRICTED
    "Samarinda":                {"status": "RESTRICTED",   "max_draft": 7.0,  "max_loa": None, "notes": "River port. Ballast entry only. Tidal. Load coal only."},
    "Gresik":                   {"status": "RESTRICTED",   "max_draft": 9.0,  "max_loa": None, "notes": "Marginal draft. Tidal restrictions."},
    "Padang":                   {"status": "RESTRICTED",   "max_draft": 9.0,  "max_loa": None, "notes": "Tidal. Partial cargo only."},
    "Tarakan Island":           {"status": "RESTRICTED",   "max_draft": 8.0,  "max_loa": None, "notes": "Ballast entry only."},

    # Philippines — EXCELLENT
    "Limay":                    {"status": "EXCELLENT",    "max_draft": 12.0, "max_loa": None, "notes": "Coal discharge - Manila Bay"},
    "Mariveles":                {"status": "EXCELLENT",    "max_draft": 12.0, "max_loa": None, "notes": "Bulk terminal Manila Bay"},
    "Calaca":                   {"status": "EXCELLENT",    "max_draft": 11.0, "max_loa": None, "notes": "Coal discharge power plant"},
    "Cebu":                     {"status": "EXCELLENT",    "max_draft": 11.0, "max_loa": None, "notes": "Central Visayas hub"},
    "General Santos":           {"status": "EXCELLENT",    "max_draft": 11.0, "max_loa": None, "notes": "Mindanao bulk port"},
    "Davao":                    {"status": "EXCELLENT",    "max_draft": 11.0, "max_loa": None, "notes": "Mindanao main port"},
    "Cagayan de Oro":           {"status": "EXCELLENT",    "max_draft": 10.0, "max_loa": None, "notes": "North Mindanao port"},
    "Iloilo City":              {"status": "GOOD",         "max_draft": 10.0, "max_loa": None, "notes": "Western Visayas. Limited berths."},
    "Subic Bay":                {"status": "EXCELLENT",    "max_draft": 14.0, "max_loa": None, "notes": "Freeport - deep water"},
    "Batangas":                 {"status": "EXCELLENT",    "max_draft": 12.0, "max_loa": None, "notes": "South Luzon bulk port"},
    "Isabel":                   {"status": "EXCELLENT",    "max_draft": 11.0, "max_loa": None, "notes": "Leyte - nickel ore loading"},
    "Surigao":                  {"status": "EXCELLENT",    "max_draft": 11.0, "max_loa": None, "notes": "Mindanao nickel ore"},
    "Nonoc":                    {"status": "EXCELLENT",    "max_draft": 12.0, "max_loa": None, "notes": "Nickel ore loading"},
    "Tagoloan":                 {"status": "EXCELLENT",    "max_draft": 11.0, "max_loa": None, "notes": "Coal discharge Mindanao"},

    # Vietnam — EXCELLENT
    "Ho Chi Minh (Cai Mep)":   {"status": "EXCELLENT",    "max_draft": 14.0, "max_loa": None, "notes": "Deep water terminal south"},
    "Nghi Son":                 {"status": "EXCELLENT",    "max_draft": 15.0, "max_loa": None, "notes": "Coal + clinker north Vietnam"},
    "Hai Phong":                {"status": "EXCELLENT",    "max_draft": 10.0, "max_loa": None, "notes": "North Vietnam main port"},
    "Vung Tau":                 {"status": "EXCELLENT",    "max_draft": 12.0, "max_loa": None, "notes": "South Vietnam offshore terminal"},
    "Quy Nhon":                 {"status": "EXCELLENT",    "max_draft": 11.0, "max_loa": None, "notes": "Central Vietnam bulk port"},
    "Da Nang":                  {"status": "EXCELLENT",    "max_draft": 11.0, "max_loa": None, "notes": "Central Vietnam main port"},
    "Cam Ranh":                 {"status": "EXCELLENT",    "max_draft": 12.0, "max_loa": None, "notes": "South-central Vietnam deep port"},
    "Vinh":                     {"status": "GOOD",         "max_draft": 9.5,  "max_loa": None, "notes": "North Vietnam. Marginal draft."},

    # Malaysia — EXCELLENT
    "Port Kelang":              {"status": "EXCELLENT",    "max_draft": 17.0, "max_loa": None, "notes": "Main Malaysian port - Westport + Northport"},
    "Lumut":                    {"status": "EXCELLENT",    "max_draft": 16.0, "max_loa": None, "notes": "Coal discharge - Perak"},
    "Johor (Pasir Gudang)":     {"status": "EXCELLENT",    "max_draft": 13.0, "max_loa": None, "notes": "South Malaysia bulk port"},
    "Penang (Butterworth)":     {"status": "EXCELLENT",    "max_draft": 12.0, "max_loa": None, "notes": "North Malaysia bulk terminal"},
    "Kemaman":                  {"status": "EXCELLENT",    "max_draft": 12.0, "max_loa": None, "notes": "East coast Malaysia"},
    "Kuantan":                  {"status": "EXCELLENT",    "max_draft": 12.0, "max_loa": None, "notes": "East coast Malaysia bulk"},
    "Bintulu":                  {"status": "EXCELLENT",    "max_draft": 13.0, "max_loa": None, "notes": "Sarawak LNG + bulk"},
    "Lahad Datu":               {"status": "GOOD",         "max_draft": 10.0, "max_loa": None, "notes": "Sabah - PKE loading"},

    # Thailand — EXCELLENT / RESTRICTED
    "Koh Sichang":              {"status": "EXCELLENT",    "max_draft": 14.0, "max_loa": None, "notes": "Coal discharge - Gulf of Thailand"},
    "Laem Chabang":             {"status": "EXCELLENT",    "max_draft": 16.0, "max_loa": None, "notes": "Major deep water port Thailand"},
    "Map Ta Phut":              {"status": "EXCELLENT",    "max_draft": 17.0, "max_loa": None, "notes": "Industrial port - coal + chemicals"},
    "Bangkok (Khlong Toei)":    {"status": "RESTRICTED",   "max_draft": 8.2,  "max_loa": 170,  "notes": "River port. Tidal. LOA restricted. Congested."},
    "Songkhla":                 {"status": "RESTRICTED",   "max_draft": 8.0,  "max_loa": None, "notes": "Shallow channel. Reduced draft only."},

    # Singapore
    "Singapore":                {"status": "EXCELLENT",    "max_draft": 20.0, "max_loa": None, "notes": "World hub port - all facilities"},

    # Bangladesh — GOOD / RESTRICTED
    "Chittagong":               {"status": "GOOD",         "max_draft": 10.0, "max_loa": None, "notes": "Main Bangladesh port. Congested."},
    "Matarbari":                {"status": "EXCELLENT",    "max_draft": 18.0, "max_loa": None, "notes": "New deep water coal terminal"},
    "Mongla":                   {"status": "RESTRICTED",   "max_draft": 7.5,  "max_loa": None, "notes": "River port. Very restricted. Tidal only."},

    # Myanmar — RESTRICTED
    "Yangon":                   {"status": "RESTRICTED",   "max_draft": 9.1,  "max_loa": None, "notes": "Tidal river. Marginal. High risk."},

    # Cambodia — NOT_SUITABLE
    "Phnom Penh":               {"status": "NOT_SUITABLE", "max_draft": 5.5,  "max_loa": None, "notes": "River port. Too shallow for any 20K DWT."},
    "Kampot":                   {"status": "NOT_SUITABLE", "max_draft": 5.0,  "max_loa": None, "notes": "Coastal river. Cannot accommodate vessel."},
    "Koh Kong":                 {"status": "NOT_SUITABLE", "max_draft": 6.0,  "max_loa": None, "notes": "Small river port. Not suitable."},

    # Timor-Leste — RESTRICTED
    "Dili":                     {"status": "RESTRICTED",   "max_draft": 8.0,  "max_loa": None, "notes": "Limited infrastructure. Reduced draft only."},
}

# Ports that simulation should NEVER send vessel to (hard block)
NOT_SUITABLE_PORTS = {
    p for p, v in PORT_SUITABILITY.items()
    if v["status"] == "NOT_SUITABLE"
}

# Ports that require tidal waiting penalty (add to port stay days)
RESTRICTED_PORTS = {
    p: v for p, v in PORT_SUITABILITY.items()
    if v["status"] == "RESTRICTED"
}

# Tidal waiting penalty in days for restricted ports
TIDAL_PENALTY_DAYS = {
    "Samarinda":             0.5,
    "Bangkok (Khlong Toei)": 1.5,
    "Mongla":                1.0,
    "Yangon":                1.0,
    "Songkhla":              0.5,
    "Dili":                  0.5,
    "Gresik":                0.5,
    "Padang":                0.5,
    "Tarakan Island":        0.5,
}


# Hard draft limits for discharge ports — vessel blocked if laden draft exceeds value.
# These mirror RESTRICTED_PORTS entries but are checked explicitly as a first-pass
# guard to prevent the simulation from routing a laden vessel to these ports.
DISCHARGE_BLOCKED_PORTS = {
    'Bangkok (Khlong Toei)': 8.2,
    'Meulaboh':              8.0,
    'Gresik':                9.0,
    'Padang':                9.0,
    'Samarinda':             7.0,
    'Mongla':                7.5,
    'Yangon':                9.1,
    'Songkhla':              8.0,
    'Dili':                  8.0,
    'Tarakan Island':        8.0,
}


def get_port_status(port_name: str) -> str:
    """Return suitability status for a port. Default EXCELLENT if unknown."""
    return PORT_SUITABILITY.get(port_name, {}).get("status", "EXCELLENT")


def is_port_blocked(port_name: str) -> bool:
    """Return True if vessel cannot enter port under any condition."""
    return port_name in NOT_SUITABLE_PORTS


def is_port_restricted(port_name: str) -> bool:
    """Return True if port has conditional/tidal restrictions."""
    return port_name in RESTRICTED_PORTS


def get_tidal_penalty(port_name: str) -> float:
    """Return additional waiting days for restricted ports."""
    return TIDAL_PENALTY_DAYS.get(port_name, 0.0)


def validate_port_for_vessel(port_name: str, laden_draft: float = 9.5,
                              ballast_draft: float = 5.5,
                              loa: float = 150.0) -> dict:
    """
    Check if a port can be called by the vessel.
    Returns dict with:
      - can_call_laden:   bool
      - can_call_ballast: bool
      - status:           str
      - max_draft:        float
      - tidal_penalty:    float
      - notes:            str
    """
    info = PORT_SUITABILITY.get(port_name, {
        "status": "EXCELLENT", "max_draft": 99.0,
        "max_loa": None, "notes": "Unknown port - assumed accessible",
    })

    max_draft = info.get("max_draft", 99.0)
    max_loa   = info.get("max_loa")
    status    = info.get("status", "EXCELLENT")

    loa_ok = (max_loa is None) or (loa <= max_loa)

    can_laden   = (laden_draft   <= max_draft) and loa_ok and (status != "NOT_SUITABLE")
    can_ballast = (ballast_draft <= max_draft) and loa_ok and (status != "NOT_SUITABLE")

    return {
        "can_call_laden":   can_laden,
        "can_call_ballast": can_ballast,
        "status":           status,
        "max_draft":        max_draft,
        "tidal_penalty":    get_tidal_penalty(port_name),
        "notes":            info.get("notes", ""),
    }
