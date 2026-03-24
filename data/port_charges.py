"""
SEA Port Charges & Congestion Database
All-in navigation costs per port call for ~17,500 GT / 17,556 DWT handy-size bulk carrier.
Sources: 2025-2026 market rates; includes pilotage, towage, berth/anchorage, port dues, agency, customs.
Excludes stevedoring (FIO default — see STEVEDORING_RATES).

Structure per port:
  nav          — USD all-in navigation per port call
  cong_mean    — average waiting/congestion days before berth
  cong_std     — standard deviation of congestion days
  note         — optional description
"""

# ─── PER-PORT CHARGES ────────────────────────────────────────────────────────
# Any port not listed here falls back to country defaults (PORT_CHARGES_DEFAULT).

PORT_CHARGES = {

    # ── INDONESIA ─────────────────────────────────────────────────────────────
    # Coal anchorages — low charges because anchorage ops, no berth hire, minimal towage
    'Taboneo - Banjarmasin': {'nav': 7500,  'cong_mean': 1.5, 'cong_std': 0.8},
    'Adang Bay':             {'nav': 6500,  'cong_mean': 1.5, 'cong_std': 0.8},
    'Muara Satui':           {'nav': 7000,  'cong_mean': 1.5, 'cong_std': 0.8},
    'Muara Pantai':          {'nav': 7000,  'cong_mean': 1.5, 'cong_std': 0.8},
    'Muara Berau':           {'nav': 7500,  'cong_mean': 1.0, 'cong_std': 0.5},
    'Muara Jawa':            {'nav': 7000,  'cong_mean': 1.0, 'cong_std': 0.5},
    'Muara Banyuasin':       {'nav': 7000,  'cong_mean': 1.0, 'cong_std': 0.5},
    'Bontang':               {'nav': 7500,  'cong_mean': 1.5, 'cong_std': 0.8},
    'Senipah Terminal':      {'nav': 7500,  'cong_mean': 1.0, 'cong_std': 0.5},
    'Tanjung Bara CT':       {'nav': 8000,  'cong_mean': 1.5, 'cong_std': 0.8},
    'Asam Asam':             {'nav': 7000,  'cong_mean': 1.5, 'cong_std': 0.8},
    'Bunati':                {'nav': 6500,  'cong_mean': 2.0, 'cong_std': 1.0},
    'Laut Island':           {'nav': 7000,  'cong_mean': 1.5, 'cong_std': 0.8},
    'Kotabaru':              {'nav': 7000,  'cong_mean': 1.5, 'cong_std': 0.8},
    'Sangkulirang':          {'nav': 6500,  'cong_mean': 1.0, 'cong_std': 0.5},
    'Bunyu':                 {'nav': 6500,  'cong_mean': 1.0, 'cong_std': 0.5},
    'Tarakan Island':        {'nav': 7000,  'cong_mean': 1.0, 'cong_std': 0.5},
    'Bengalon':              {'nav': 6500,  'cong_mean': 1.0, 'cong_std': 0.5},
    'Samarinda':             {'nav': 8000,  'cong_mean': 1.5, 'cong_std': 0.8},
    # Major / secondary Indonesian ports
    'Balikpapan':            {'nav': 15000, 'cong_mean': 0.75, 'cong_std': 0.4},
    'Jakarta':               {'nav': 16000, 'cong_mean': 1.5,  'cong_std': 0.8},
    'Tanjung Priok':         {'nav': 16000, 'cong_mean': 1.5,  'cong_std': 0.8},
    'Surabaya':              {'nav': 14000, 'cong_mean': 1.5,  'cong_std': 0.7},
    'Gresik':                {'nav': 13000, 'cong_mean': 1.5,  'cong_std': 0.7},
    'Semarang':              {'nav': 13000, 'cong_mean': 1.0,  'cong_std': 0.5},
    'Paiton':                {'nav': 10000, 'cong_mean': 1.0,  'cong_std': 0.5},
    'Tanjung Tapa':          {'nav': 7530,  'cong_mean': 1.0,  'cong_std': 0.5},
    'Tanjung Emas':          {'nav': 13000, 'cong_mean': 1.0,  'cong_std': 0.5},
    'Cilacap':               {'nav': 12000, 'cong_mean': 1.0,  'cong_std': 0.5},
    'Pelabuhan Ratu':        {'nav': 10000, 'cong_mean': 1.0,  'cong_std': 0.5},
    'Tarahan':               {'nav': 10000, 'cong_mean': 1.0,  'cong_std': 0.5},
    'Padang':                {'nav': 10000, 'cong_mean': 1.0,  'cong_std': 0.5},
    'Bahudopi':              {'nav': 6500,  'cong_mean': 1.0,  'cong_std': 0.5},
    'Weda Bay':              {'nav': 6500,  'cong_mean': 1.0,  'cong_std': 0.5},
    'Belawan':               {'nav': 12000, 'cong_mean': 1.0,  'cong_std': 0.5},
    'Kuala Tanjung':         {'nav': 12000, 'cong_mean': 1.0,  'cong_std': 0.5},
    'Dumai':                 {'nav': 11000, 'cong_mean': 0.75, 'cong_std': 0.4},
    'Panjang':               {'nav': 10000, 'cong_mean': 1.0,  'cong_std': 0.5},
    'Makassar':              {'nav': 13000, 'cong_mean': 1.0,  'cong_std': 0.5},
    'Kupang':                {'nav': 9000,  'cong_mean': 0.5,  'cong_std': 0.3},

    # ── PHILIPPINES ───────────────────────────────────────────────────────────
    'Manila':                {'nav': 22000, 'cong_mean': 3.0,  'cong_std': 1.5},
    'Manila South Harbour':  {'nav': 20000, 'cong_mean': 3.0,  'cong_std': 1.5},
    'Batangas':              {'nav': 18000, 'cong_mean': 1.5,  'cong_std': 0.8},
    'Limay':                 {'nav': 14000, 'cong_mean': 0.75, 'cong_std': 0.4},
    'Mariveles':             {'nav': 13000, 'cong_mean': 0.75, 'cong_std': 0.4},
    'Pagbilao':              {'nav': 14000, 'cong_mean': 0.75, 'cong_std': 0.4},
    'Quezon Power Plant':    {'nav': 14000, 'cong_mean': 0.75, 'cong_std': 0.4},
    'Quezon':                {'nav': 14000, 'cong_mean': 0.75, 'cong_std': 0.4},
    'Masinloc':              {'nav': 13000, 'cong_mean': 0.5,  'cong_std': 0.3},
    'Sual':                  {'nav': 13000, 'cong_mean': 0.5,  'cong_std': 0.3},
    'Davao':                 {'nav': 12000, 'cong_mean': 0.75, 'cong_std': 0.4},
    'Villanueva':            {'nav': 11000, 'cong_mean': 0.5,  'cong_std': 0.3},
    'Kauswagan':             {'nav': 11000, 'cong_mean': 0.5,  'cong_std': 0.3},
    'General Santos':        {'nav': 12000, 'cong_mean': 0.5,  'cong_std': 0.3},
    'Toledo':                {'nav': 11000, 'cong_mean': 0.5,  'cong_std': 0.3},
    'Iloilo':                {'nav': 11000, 'cong_mean': 0.5,  'cong_std': 0.3},
    'Naga (Cebu)':           {'nav': 11000, 'cong_mean': 0.5,  'cong_std': 0.3},
    'Naga':                  {'nav': 11000, 'cong_mean': 0.5,  'cong_std': 0.3},
    'Cebu':                  {'nav': 13000, 'cong_mean': 0.75, 'cong_std': 0.4},
    'Subic Bay':             {'nav': 15000, 'cong_mean': 0.5,  'cong_std': 0.3},

    # ── VIETNAM ───────────────────────────────────────────────────────────────
    'Hai Phong':             {'nav': 18000, 'cong_mean': 2.0,  'cong_std': 1.0},
    'Ho Chi Minh City':      {'nav': 17000, 'cong_mean': 1.5,  'cong_std': 0.8},
    'Cai Mep':               {'nav': 16000, 'cong_mean': 1.0,  'cong_std': 0.5},
    'Campha':                {'nav': 12000, 'cong_mean': 1.5,  'cong_std': 0.8},
    'Ha Long':               {'nav': 12000, 'cong_mean': 1.5,  'cong_std': 0.8},
    'Go Gia':                {'nav': 11000, 'cong_mean': 1.0,  'cong_std': 0.5},
    'Dung Quat':             {'nav': 14000, 'cong_mean': 1.0,  'cong_std': 0.5},
    'Phu My':                {'nav': 13000, 'cong_mean': 1.0,  'cong_std': 0.5},
    'Nghi Son':              {'nav': 13000, 'cong_mean': 1.0,  'cong_std': 0.5},
    'Da Nang':               {'nav': 14000, 'cong_mean': 1.0,  'cong_std': 0.5},
    'Qui Nhon':              {'nav': 12000, 'cong_mean': 0.75, 'cong_std': 0.4},
    'Vung Tau':              {'nav': 14000, 'cong_mean': 1.0,  'cong_std': 0.5},
    'Quang Ninh':            {'nav': 12000, 'cong_mean': 1.5,  'cong_std': 0.8},

    # ── THAILAND ──────────────────────────────────────────────────────────────
    'Koh Sichang':           {'nav': 10000, 'cong_mean': 0.75, 'cong_std': 0.4},
    'Ko Por Anchorage':      {'nav': 10000, 'cong_mean': 0.75, 'cong_std': 0.4},
    'Laem Chabang':          {'nav': 18000, 'cong_mean': 0.75, 'cong_std': 0.4},
    'Map Ta Phut':           {'nav': 17000, 'cong_mean': 0.75, 'cong_std': 0.4},
    'Bangkok':               {'nav': 15000, 'cong_mean': 2.0,  'cong_std': 1.0},
    'Sriracha':              {'nav': 12000, 'cong_mean': 0.5,  'cong_std': 0.3},
    'Songkhla':              {'nav': 11000, 'cong_mean': 0.5,  'cong_std': 0.3},

    # ── MALAYSIA ──────────────────────────────────────────────────────────────
    'Port Kelang':           {'nav': 20000, 'cong_mean': 1.5,  'cong_std': 0.8},
    'Tanjung Pelepas':       {'nav': 20000, 'cong_mean': 0.75, 'cong_std': 0.4},
    'Lumut':                 {'nav': 14000, 'cong_mean': 0.75, 'cong_std': 0.4},
    'Port Dickson':          {'nav': 13000, 'cong_mean': 0.5,  'cong_std': 0.3},
    'Kuantan':               {'nav': 14000, 'cong_mean': 0.75, 'cong_std': 0.4},
    'Kemaman':               {'nav': 13000, 'cong_mean': 0.5,  'cong_std': 0.3},
    'Bintulu':               {'nav': 13000, 'cong_mean': 0.5,  'cong_std': 0.3},
    'Kuching':               {'nav': 12000, 'cong_mean': 0.5,  'cong_std': 0.3},
    'Tawau':                 {'nav': 11000, 'cong_mean': 0.5,  'cong_std': 0.3},
    'Sandakan':              {'nav': 11000, 'cong_mean': 0.5,  'cong_std': 0.3},
    'Kota Kinabalu':         {'nav': 12000, 'cong_mean': 0.5,  'cong_std': 0.3},

    # ── BANGLADESH ────────────────────────────────────────────────────────────
    'Chittagong':            {'nav': 25000, 'cong_mean': 5.5,  'cong_std': 2.5},
    'Payra':                 {'nav': 18000, 'cong_mean': 3.0,  'cong_std': 1.5},
    'Mongla':                {'nav': 20000, 'cong_mean': 4.0,  'cong_std': 2.0},

    # ── CAMBODIA ──────────────────────────────────────────────────────────────
    'Sihanoukville':         {'nav': 10000, 'cong_mean': 0.75, 'cong_std': 0.4},
    'Phnom Penh':            {'nav': 10000, 'cong_mean': 1.0,  'cong_std': 0.5},

    # ── MYANMAR ───────────────────────────────────────────────────────────────
    'Yangon':                {'nav': 13000, 'cong_mean': 2.0,  'cong_std': 1.0},
    'Thilawa':               {'nav': 12000, 'cong_mean': 1.5,  'cong_std': 0.8},
    'Mawlamyine':            {'nav': 10000, 'cong_mean': 1.0,  'cong_std': 0.5},

    # ── SINGAPORE ─────────────────────────────────────────────────────────────
    'Singapore':             {'nav': 22000, 'cong_mean': 0.5,  'cong_std': 0.3},
    'Jurong':                {'nav': 20000, 'cong_mean': 0.5,  'cong_std': 0.3},

    # ── SRI LANKA ─────────────────────────────────────────────────────────────
    'Colombo':               {'nav': 18000, 'cong_mean': 1.0,  'cong_std': 0.5},
    'Trincomalee':           {'nav': 15000, 'cong_mean': 0.75, 'cong_std': 0.4},
    'Galle':                 {'nav': 14000, 'cong_mean': 0.75, 'cong_std': 0.4},
}

# ─── COUNTRY DEFAULTS (fallback when port not in PORT_CHARGES above) ─────────
PORT_CHARGES_DEFAULT = {
    'Indonesia':   {'nav': 10000, 'cong_mean': 1.5,  'cong_std': 0.8},
    'Philippines': {'nav': 13000, 'cong_mean': 1.0,  'cong_std': 0.5},
    'Vietnam':     {'nav': 14000, 'cong_mean': 1.0,  'cong_std': 0.5},
    'Thailand':    {'nav': 13000, 'cong_mean': 1.0,  'cong_std': 0.5},
    'Malaysia':    {'nav': 14000, 'cong_mean': 0.75, 'cong_std': 0.4},
    'Bangladesh':  {'nav': 22000, 'cong_mean': 4.0,  'cong_std': 2.0},
    'Cambodia':    {'nav': 10000, 'cong_mean': 0.75, 'cong_std': 0.4},
    'Myanmar':     {'nav': 12000, 'cong_mean': 1.5,  'cong_std': 0.8},
    'Sri Lanka':   {'nav': 16000, 'cong_mean': 0.75, 'cong_std': 0.4},
    'Singapore':   {'nav': 21000, 'cong_mean': 0.5,  'cong_std': 0.3},
    'default':     {'nav': 13000, 'cong_mean': 1.0,  'cong_std': 0.5},
}


def get_port_charges(port_name: str, country: str) -> dict:
    """Return nav cost and congestion data for a given port, with country fallback."""
    if port_name in PORT_CHARGES:
        return PORT_CHARGES[port_name]
    # Partial match (e.g. 'Balikpapan SPM' matches 'Balikpapan')
    for key in PORT_CHARGES:
        if key.lower() in port_name.lower() or port_name.lower() in key.lower():
            return PORT_CHARGES[key]
    return PORT_CHARGES_DEFAULT.get(country, PORT_CHARGES_DEFAULT['default'])


# ─── STEVEDORING RATES (USD/MT) — only applies when NOT FIO ──────────────────
# Default in all sample voyages is FIO ($0). Enable per commodity via toggle.
STEVEDORING_RATES = {
    # category: (load_per_mt, disch_per_mt)
    'Coal':       (2.00, 3.00),
    'Dry Bulk':   (2.50, 3.50),
    'Agri-Bulk':  (2.75, 3.50),
    'Break-Bulk': (4.50, 6.00),
    'Steel/Metal':(6.00, 7.50),
    'Fertilizers':(2.75, 3.50),
}

# ─── COST PER WAITING DAY (charter + idle bunkers) ───────────────────────────
# Used in UI display only (congestion cost visualisation).
# Charter: $9,000 + LSFO idle: 1.5 MT × $560 + MGO idle: 1.5 MT × $780
COST_PER_CONGESTION_DAY = 9000 + (1.5 * 560) + (1.5 * 780)   # = $11,010
