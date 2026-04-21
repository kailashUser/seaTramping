"""
SEA Tramping Voyage Simulation Dashboard V2
Network graph optimisation + exact costing model + voyage-level detail + What-If editor.
"""
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import sys
import os
import time
import math
import json as _json
import requests
import re

# ── Live data helpers ──────────────────────────────────────────────────────────
VESSEL_API_KEY  = "86231bda2f1b18af2ef3a6eaac09722c63dee57d9138d93eab0a7b5e4dfb81fd"
VESSEL_API_BASE = "https://api.vesselapi.com/v1"


def fetch_vessel_from_imo(imo_number: str) -> dict:
    """Look up vessel dimensions from VesselAPI, with ShipXplorer fallback."""
    # Primary: VesselAPI
    try:
        headers = {"Authorization": f"Bearer {VESSEL_API_KEY}"}
        url = f"{VESSEL_API_BASE}/vessel/{imo_number}?filter.idType=imo"
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            vessel = resp.json().get("vessel", {})
            if vessel and vessel.get("deadweight_tonnage"):
                return {
                    "success":     True,
                    "name":        vessel.get("name", "Unknown"),
                    "imo":         vessel.get("imo", imo_number),
                    "mmsi":        vessel.get("mmsi", ""),
                    "dwt":         vessel.get("deadweight_tonnage", 0),
                    "loa":         vessel.get("length", 0),
                    "beam":        vessel.get("breadth", 0),
                    "year_built":  vessel.get("year_built", 0),
                    "flag":        vessel.get("country", ""),
                    "vessel_type": vessel.get("vessel_type", ""),
                    "owner":       vessel.get("owner_name", ""),
                    "call_sign":   vessel.get("call_sign", ""),
                    "source":      "VesselAPI",
                }
    except Exception:
        pass

    # Fallback: ShipXplorer public search
    try:
        sx_url = f"https://www.shipxplorer.com/api/vessel/imo/{imo_number}"
        sx_resp = requests.get(
            sx_url,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
            timeout=10,
        )
        if sx_resp.status_code == 200:
            d = sx_resp.json()
            if d.get("imoNumber") or d.get("imo"):
                return {
                    "success":     True,
                    "name":        d.get("shipName", d.get("name", "Unknown")),
                    "imo":         d.get("imoNumber", d.get("imo", imo_number)),
                    "mmsi":        d.get("mmsi", ""),
                    "dwt":         float(d.get("deadWeight", d.get("dwt", 0)) or 0),
                    "loa":         float(d.get("length", 0) or 0),
                    "beam":        float(d.get("width", d.get("beam", 0)) or 0),
                    "year_built":  d.get("yearOfBuild", d.get("yearBuilt", 0)),
                    "flag":        d.get("flagName", d.get("flag", "")),
                    "vessel_type": d.get("shipType", d.get("vesselType", "")),
                    "owner":       d.get("ownerName", ""),
                    "call_sign":   d.get("callSign", ""),
                    "source":      "ShipXplorer",
                }
    except Exception:
        pass

    return {"success": False, "error": f"Vessel IMO {imo_number} not found in any database."}


def fetch_bhsi_rate() -> dict:
    """Fetch current BHSI daily rate from handybulk.com."""
    try:
        resp = requests.get(
            "https://www.handybulk.com/baltic-dry-index/",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        if resp.status_code == 200:
            text = resp.text
            for pattern in [
                r'BHSI[^$]*\$\s*([\d,]+)\s*per\s*day',
                r'handysize[^$]*\$\s*([\d,]+)',
                r'BHSI.*?(\d{1,2},\d{3})',
            ]:
                m = re.search(pattern, text, re.IGNORECASE)
                if m:
                    rate = int(m.group(1).replace(",", ""))
                    if 3000 < rate < 50000:
                        return {"success": True, "rate": rate,
                                "source": "Baltic Handysize Index (handybulk.com)"}
            return {"success": False, "error": "Could not parse BHSI rate. Use manual entry."}
        return {"success": False, "error": f"HTTP {resp.status_code} from handybulk.com"}
    except Exception as e:
        return {"success": False, "error": f"Connection error: {str(e)}"}


def fetch_bunker_prices() -> dict:
    """Fetch LSFO and MGO prices from Ship & Bunker Singapore."""
    try:
        resp = requests.get(
            "https://shipandbunker.com/prices/apac/sea/sg-sin-singapore",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        if resp.status_code == 200:
            text = resp.text
            result = {"success": True}
            lm = re.search(r'VLSFO.*?\$?\s*(\d{3,4})', text, re.IGNORECASE)
            mm = re.search(r'MGO.*?\$?\s*(\d{3,4})',   text, re.IGNORECASE)
            if lm:
                result["lsfo"] = int(lm.group(1))
            if mm:
                result["mgo"]  = int(mm.group(1))
            if "lsfo" in result or "mgo" in result:
                result["source"] = "Ship & Bunker Singapore"
                return result
            return {"success": False, "error": "Could not parse bunker prices. Use manual entry."}
        return {"success": False, "error": f"HTTP {resp.status_code} from Ship & Bunker"}
    except Exception as e:
        return {"success": False, "error": f"Connection error: {str(e)}"}

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.data_processor import (
    load_and_process_data, build_port_database, build_distance_matrix,
    build_leg_library, COMMODITY_23, COMMODITY_CATEGORIES, FREIGHT_RATE_PARAMS,
    PORT_CHARGES_BY_COUNTRY, HANDLING_COST
)
from modules.simulation_engine import (
    VesselConfig, SimConfig,
    run_full_simulation, analyse_results,
    build_voyage_graph, compute_port_centrality, find_communities,
    cascade_recalculate_legs, FastLegLibrary, _find_leg_idx,
    HAS_NX,
)
from modules.sim_logger import build_simulation_log, write_simulation_log

st.set_page_config(page_title="SEA Tramping Simulation V2", layout="wide", page_icon="🚢")

st.markdown("""
<style>
    .metric-card {background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.2rem; border-radius: 12px; color: white; text-align: center;}
    .metric-value {font-size: 1.8rem; font-weight: 700;}
    .metric-label {font-size: 0.85rem; opacity: 0.9;}
    .stTabs [data-baseweb="tab-list"] {gap: 8px;}
    .stTabs [data-baseweb="tab"] {padding: 10px 20px; font-weight: 600;}
    .profit-pos {color: #22c55e; font-weight: 700;}
    .profit-neg {color: #ef4444; font-weight: 700;}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div style="
    background:linear-gradient(135deg,#1a3a5c 0%,#2d5986 60%,#667eea 100%);
    padding:20px 28px 16px;
    border-radius:12px;
    margin-bottom:24px;
">
    <div style="font-size:2rem;font-weight:700;color:white;letter-spacing:-0.5px;">
        🚢 SEA Tramping Voyage Optimiser
    </div>
    <div style="font-size:0.95rem;color:rgba(255,255,255,0.75);margin-top:4px;">
        Monte Carlo &nbsp;|&nbsp;
        Dual Fuel Exact Costing &nbsp;|&nbsp;
        Voyage Dependency Cascade &nbsp;|&nbsp;
        
    </div>
</div>
""", unsafe_allow_html=True)


@st.cache_data(ttl=3600)
def fetch_live_bunker_prices():
    """
    Fetch live bunker prices from Ship & Bunker (Singapore).
    Returns dict with LSFO and MGO prices, or None on failure.
    Falls back silently if network is unavailable.
    """
    try:
        import requests
        from bs4 import BeautifulSoup
        url = "https://shipandbunker.com/prices/apac/sea/sg-sin-singapore"
        headers = {'User-Agent': 'Mozilla/5.0 (compatible; research bot)'}
        r = requests.get(url, headers=headers, timeout=8)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, 'html.parser')
        prices = {}
        for row in soup.select('table tr'):
            cells = row.find_all('td')
            if len(cells) >= 2:
                fuel = cells[0].get_text(strip=True).upper()
                price_text = cells[1].get_text(strip=True).replace(',', '')
                try:
                    price = float(price_text)
                    if 'VLSFO' in fuel or 'LSFO' in fuel:
                        prices['lsfo'] = price
                    elif 'MGO' in fuel:
                        prices['mgo'] = price
                except ValueError:
                    pass
        return prices if prices else None
    except Exception:
        return None


def export_programme_to_excel(prog, vessel_config, programme_rank):
    """
    Export a voyage programme to a formatted Excel workbook matching the
    company tramping spreadsheet layout.
    Returns bytes object ready for st.download_button.
    """
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    import io

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"Programme #{programme_rank}"

    header_fill  = PatternFill("solid", fgColor="1a3a5c")
    subhead_fill = PatternFill("solid", fgColor="667eea")
    alt_fill     = PatternFill("solid", fgColor="f0f4ff")
    total_fill   = PatternFill("solid", fgColor="22c55e")
    white_font   = Font(color="FFFFFF", bold=True, size=10)
    bold_font    = Font(bold=True, size=10)
    normal_font  = Font(size=10)
    money_fmt    = '#,##0'
    rate_fmt     = '#,##0.00'
    thin_border  = Border(bottom=Side(style='thin', color='cccccc'))

    # Title block
    ws.merge_cells('A1:AC1')
    ws['A1'] = f"SEA Tramping Voyage Programme #{programme_rank} — Annual P&L"
    ws['A1'].font = Font(color="FFFFFF", bold=True, size=13)
    ws['A1'].fill = header_fill
    ws['A1'].alignment = Alignment(horizontal='center', vertical='center')
    ws.row_dimensions[1].height = 28

    ws.merge_cells('A2:AC2')
    ws['A2'] = (
        f"Vessel DWT: {vessel_config.dwt:,} MT  |  "
        f"DWCC: {vessel_config.dwcc:,} MT  |  "
        f"Speed: {vessel_config.speed_laden_knots}/{vessel_config.speed_ballast_knots} kn  |  "
        f"Charter Hire: ${vessel_config.charter_hire_day:,}/day  |  "
        f"LSFO: ${vessel_config.lsfo_price_mt}/MT  |  "
        f"MGO: ${vessel_config.mgo_price_mt}/MT"
    )
    ws['A2'].font = Font(size=9, italic=True)
    ws['A2'].alignment = Alignment(horizontal='center')
    ws.row_dimensions[2].height = 16

    headers = [
        'Voy #', 'Ballast From', 'Load Port', 'Disch Port', 'Commodity',
        'Cargo MT', 'Rate $/MT', 'Gross Freight',
        'Brokerage', 'Net Income',
        'Charter Hire', 'LSFO MT', 'MGO MT', 'LSFO Cost', 'MGO Cost',
        'Total Bunker', 'Load Port Nav', 'Disch Port Nav', 'Port Costs',
        'Insurance', 'Other Costs', 'Total Expenses',
        'Profit / Loss', '$/Day', '$/MT',
        'Ballast NM', 'Laden NM', 'Ballast Days', 'Laden Days',
        'Port Days', 'Cong Days', 'Total Days', 'Cum Profit',
    ]
    col_widths = [
        6, 16, 16, 16, 18,
        10, 9, 14,
        11, 14,
        14, 9, 9, 13, 13,
        13, 14, 14, 13,
        11, 11, 14,
        14, 11, 9,
        11, 11, 12, 12,
        11, 11, 12, 14,
    ]
    for ci, (h, w) in enumerate(zip(headers, col_widths), 1):
        cell = ws.cell(row=3, column=ci, value=h)
        cell.font = white_font
        cell.fill = subhead_fill
        cell.alignment = Alignment(horizontal='center', wrap_text=True)
        cell.border = thin_border
        ws.column_dimensions[get_column_letter(ci)].width = w
    ws.row_dimensions[3].height = 32
    ws.freeze_panes = 'A4'

    legs = prog['legs']
    for ri, leg in enumerate(legs):
        row = 4 + ri
        fill = alt_fill if ri % 2 == 0 else None
        g   = leg.get('gross_freight', leg.get('revenue', 0))
        br  = leg.get('brokerage', g * (vessel_config.brokerage_pct if vessel_config else 0.0375))
        ni  = leg.get('net_income', g - br)
        lc  = leg.get('lsfo_cost', 0)
        mc  = leg.get('mgo_cost', 0)
        tb  = lc + mc
        ch  = leg.get('charter_hire', leg.get('charter_hire_cost', 0))
        pc  = leg.get('port_costs',
              leg.get('load_port_nav', 0) + leg.get('disch_port_nav', 0))
        ins = leg.get('insurance', 0)
        oth = leg.get('other_costs', 1000)
        exp = leg.get('total_expenses', leg.get('total_cost', 0))
        pl  = leg.get('profit_loss', leg.get('profit', 0))
        ppd = leg.get('profit_per_day', 0)
        pmt = leg.get('profit_per_mt', 0)
        cum = leg.get('cum_profit', 0)

        values = [
            ri + 1,
            leg.get('ballast_from_port', '—'),
            leg.get('origin_port', ''),
            leg.get('dest_port', ''),
            leg.get('commodity', ''),
            leg.get('cargo_mt', 0),
            leg.get('freight_rate', 0),
            g, br, ni,
            ch,
            leg.get('lsfo_mt', 0),
            leg.get('mgo_mt', 0),
            lc, mc, tb,
            leg.get('load_port_nav', 0),
            leg.get('disch_port_nav', 0),
            pc, ins, oth, exp,
            pl, ppd, pmt,
            leg.get('ballast_nm', leg.get('ballast_distance_nm', 0)),
            leg.get('laden_nm', leg.get('distance_nm', 0)),
            leg.get('ballast_days', leg.get('sailing_days_ballast', 0)),
            leg.get('laden_days', leg.get('sailing_days_laden', 0)),
            leg.get('port_days', 0),
            leg.get('congestion_days', 0),
            leg.get('total_days', 0),
            cum,
        ]
        money_cols = {8, 9, 10, 11, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 33}
        for ci, val in enumerate(values, 1):
            cell = ws.cell(row=row, column=ci, value=val)
            cell.font = normal_font
            cell.alignment = Alignment(horizontal='right' if ci > 5 else 'left')
            if fill:
                cell.fill = fill
            if ci in money_cols and isinstance(val, (int, float)):
                cell.number_format = money_fmt
            elif ci in {7, 24, 25} and isinstance(val, (int, float)):
                cell.number_format = rate_fmt
        pl_cell = ws.cell(row=row, column=23)
        if pl > 0:
            pl_cell.font = Font(color="166534", bold=True, size=10)
        elif pl < 0:
            pl_cell.font = Font(color="991b1b", bold=True, size=10)

    # Totals row
    tr = 4 + len(legs)
    ws.cell(row=tr, column=1, value='TOTAL').font = bold_font
    total_cols = {
        8:  sum(l.get('gross_freight', l.get('revenue', 0)) for l in legs),
        9:  sum(l.get('brokerage', 0) for l in legs),
        10: sum(l.get('net_income', 0) for l in legs),
        11: sum(l.get('charter_hire', l.get('charter_hire_cost', 0)) for l in legs),
        16: sum(l.get('lsfo_cost', 0) + l.get('mgo_cost', 0) for l in legs),
        19: sum(l.get('port_costs', 0) for l in legs),
        20: sum(l.get('insurance', 0) for l in legs),
        22: sum(l.get('total_expenses', l.get('total_cost', 0)) for l in legs),
        23: sum(l.get('profit_loss', l.get('profit', 0)) for l in legs),
        32: sum(l.get('total_days', 0) for l in legs),
    }
    for ci, val in total_cols.items():
        cell = ws.cell(row=tr, column=ci, value=val)
        cell.font = Font(bold=True, color="FFFFFF", size=10)
        cell.fill = total_fill
        cell.number_format = money_fmt if ci != 32 else '#,##0.0'

    # P&L Summary sheet
    ws2 = wb.create_sheet("Annual P&L Summary")
    total_gross  = sum(l.get('gross_freight', l.get('revenue', 0)) for l in legs)
    total_broker = sum(l.get('brokerage', 0) for l in legs)
    total_ni     = total_gross - total_broker
    total_hire   = sum(l.get('charter_hire', l.get('charter_hire_cost', 0)) for l in legs)
    total_lsfo   = sum(l.get('lsfo_cost', 0) for l in legs)
    total_mgo    = sum(l.get('mgo_cost', 0) for l in legs)
    total_port   = sum(l.get('port_costs', 0) for l in legs)
    total_ins    = sum(l.get('insurance', 0) for l in legs)
    total_other  = sum(l.get('other_costs', 1000) for l in legs)
    total_exp    = sum(l.get('total_expenses', l.get('total_cost', 0)) for l in legs)
    total_pl     = total_ni - total_exp
    total_days   = sum(l.get('total_days', 0) for l in legs)
    tce          = (total_ni - total_port - total_ins - total_other) / max(total_days, 1)

    pl_lines = [
        ("INCOME", None),
        ("Gross Freight Revenue", total_gross),
        ("  Less: Brokerage (3.75%)", -total_broker),
        ("Net Income", total_ni),
        ("", None),
        ("EXPENSES", None),
        ("Charter Hire", -total_hire),
        ("Bunker — LSFO", -total_lsfo),
        ("Bunker — MGO", -total_mgo),
        ("Total Bunker Cost", -(total_lsfo + total_mgo)),
        ("Port Navigation Costs", -total_port),
        ("Insurance", -total_ins),
        ("Other Costs", -total_other),
        ("Total Expenses", -total_exp),
        ("", None),
        ("NET PROFIT / LOSS", total_pl),
        ("", None),
        ("KPIs", None),
        ("TCE ($/day)", tce),
        ("Total Operating Days", total_days),
        ("Number of Voyages", len(legs)),
        ("Avg Profit per Voyage", total_pl / max(len(legs), 1)),
    ]
    ws2.column_dimensions['A'].width = 32
    ws2.column_dimensions['B'].width = 18
    for ri, (label, val) in enumerate(pl_lines, 1):
        lc = ws2.cell(row=ri, column=1, value=label)
        if val is None:
            lc.font = Font(bold=True, size=11)
            lc.fill = PatternFill("solid", fgColor="e8edf7")
        else:
            lc.font = Font(size=10)
            vc = ws2.cell(row=ri, column=2, value=val)
            vc.number_format = money_fmt
            vc.alignment = Alignment(horizontal='right')
            if label == "NET PROFIT / LOSS":
                lc.font = Font(bold=True, size=12)
                vc.font = Font(bold=True, size=12,
                               color="166534" if val >= 0 else "991b1b")
            elif label.startswith("TCE"):
                vc.number_format = '#,##0'

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output.getvalue()


@st.cache_data
def load_data(excel_path):
    intra = load_and_process_data(excel_path)
    ports = build_port_database(intra, n_ports=70)
    dist_matrix = build_distance_matrix(ports)
    legs = build_leg_library(ports, dist_matrix, intra)
    return intra, ports, dist_matrix, legs


# ─── SIMULATION STATE FLAGS ──────────────────────────────────────────────────
if 'sim_running' not in st.session_state:
    st.session_state['sim_running'] = False
if 'sim_done' not in st.session_state:
    st.session_state['sim_done'] = False
if 'sim_requested' not in st.session_state:
    st.session_state['sim_requested'] = False
_sim_locked = st.session_state.get('sim_running', False)

# ─── SIDEBAR ─────────────────────────────────────────────────────────────────

# ── 🚢 Vessel Configuration ───────────────────────────────────────────────────
st.sidebar.markdown("### 🚢 Vessel")

# IMO Lookup row
imo_col1, imo_col2 = st.sidebar.columns([3, 1])
with imo_col1:
    imo_input = st.text_input(
        "IMO Number",
        value=st.session_state.get("imo_number", ""),
        placeholder="e.g. 9128805",
        key="imo_input_field",
        label_visibility="collapsed",
    )
with imo_col2:
    lookup_btn = st.button("🔍", key="imo_lookup_btn",
                           help="Lookup vessel from VesselAPI")

if lookup_btn and imo_input.strip():
    with st.spinner("Looking up vessel..."):
        _imo_result = fetch_vessel_from_imo(imo_input.strip())
    if _imo_result["success"]:
        st.session_state["_pending_imo"] = _imo_result
    else:
        st.sidebar.error(_imo_result["error"])

# Pending vessel verification banner
if st.session_state.get("_pending_imo"):
    _p = st.session_state["_pending_imo"]
    _vtype = _p.get("vessel_type", "Unknown type")
    _src   = _p.get("source", "API")
    _is_bulk = any(kw in _vtype.lower() for kw in ("bulk", "handy", "supra", "panamax", "capesize"))
    _warn_color = "#1a3a5c" if _is_bulk else "#7c2d12"
    _warn_label = "" if _is_bulk else f" ⚠️ Type: {_vtype} — confirm this is correct"
    st.sidebar.markdown(
        f"<div style='background:{_warn_color};border:1px solid #334155;"
        f"border-radius:8px;padding:8px 10px;margin:4px 0;font-size:11px;color:#e2e8f0'>"
        f"<div style='font-weight:700;font-size:13px;margin-bottom:4px'>"
        f"{_p['name']}</div>"
        f"IMO&nbsp;{_p['imo']} · MMSI&nbsp;{_p.get('mmsi','—')} · {_p.get('call_sign','')}<br>"
        f"DWT&nbsp;<b>{int(_p['dwt']):,}</b> · LOA&nbsp;{_p['loa']}m · Beam&nbsp;{_p['beam']}m<br>"
        f"Flag: {_p['flag']} · Built: {_p['year_built']}<br>"
        f"Owner: {_p.get('owner','—')[:30]}<br>"
        f"<span style='color:#94a3b8'>Source: {_src}</span>"
        f"{_warn_label}"
        f"</div>",
        unsafe_allow_html=True,
    )
    _cb1, _cb2 = st.sidebar.columns(2)
    if _cb1.button("✅ Apply", key="imo_apply_btn"):
        st.session_state["imo_number"]  = str(_p["imo"])
        st.session_state["vessel_name"] = _p["name"]
        st.session_state["vessel_imo"]  = _p["imo"]
        # api_ keys (used as value= defaults)
        st.session_state["api_dwt"]     = float(_p["dwt"])
        st.session_state["api_loa"]     = float(_p["loa"])
        st.session_state["api_beam"]    = float(_p["beam"])
        st.session_state["api_year"]    = _p["year_built"]
        st.session_state["api_flag"]    = _p["flag"]
        # widget keys — must be set directly so number_inputs update
        if _p["dwt"]:
            st.session_state["vessel_dwt"]  = int(float(_p["dwt"]))
        if _p["loa"]:
            st.session_state["vessel_loa"]  = int(float(_p["loa"]))
        if _p["beam"]:
            st.session_state["vessel_beam"] = int(float(_p["beam"]))
        st.session_state.pop("_pending_imo", None)
        st.rerun()
    if _cb2.button("✗ Discard", key="imo_discard_btn"):
        st.session_state.pop("_pending_imo", None)
        st.rerun()

if st.session_state.get("vessel_name"):
    st.sidebar.markdown(
        f"<div style='font-size:11px;color:#64748b;margin-bottom:4px'>"
        f"✓ {st.session_state['vessel_name']} | "
        f"IMO {st.session_state.get('vessel_imo','')} | "
        f"{st.session_state.get('api_flag','')}</div>",
        unsafe_allow_html=True,
    )

dwt_val = st.sidebar.number_input(
    "DWT (MT)",
    min_value=5000, max_value=50000,
    value=int(st.session_state.get("api_dwt", 17556)),
    step=100, key="vessel_dwt", disabled=_sim_locked,
)
dwcc_val = st.sidebar.number_input(
    "DWCC / Cargo capacity (MT)",
    min_value=3000, max_value=45000,
    value=int(st.session_state.get("vessel_dwcc_override", dwt_val * 85 // 100)),
    step=100, key="vessel_dwcc", disabled=_sim_locked,
    help="Deadweight cargo capacity — typically ~85% of DWT",
)

loa_col, beam_col = st.sidebar.columns(2)
with loa_col:
    loa_val = st.number_input(
        "LOA (m)", min_value=50, max_value=400,
        value=int(st.session_state.get("api_loa", 150)),
        step=1, key="vessel_loa", disabled=_sim_locked,
    )
with beam_col:
    beam_val = st.number_input(
        "Beam (m)", min_value=10, max_value=60,
        value=int(st.session_state.get("api_beam", 24)),
        step=1, key="vessel_beam", disabled=_sim_locked,
    )

draft_col1, draft_col2 = st.sidebar.columns(2)
with draft_col1:
    draft_laden = st.number_input(
        "Draft laden (m)", min_value=3.0, max_value=20.0,
        value=float(st.session_state.get("vessel_draft_laden", 9.5)),
        step=0.1, key="vessel_draft_laden_input", disabled=_sim_locked,
    )
with draft_col2:
    draft_ballast = st.number_input(
        "Draft ballast (m)", min_value=2.0, max_value=15.0,
        value=float(st.session_state.get("vessel_draft_ballast", 5.5)),
        step=0.1, key="vessel_draft_ballast_input", disabled=_sim_locked,
    )

spd_col1, spd_col2 = st.sidebar.columns(2)
with spd_col1:
    speed_laden = st.number_input(
        "Speed laden (kn)", min_value=6.0, max_value=20.0,
        value=11.0, step=0.5,
        key="vessel_speed_laden", disabled=_sim_locked,
    )
with spd_col2:
    speed_ballast = st.number_input(
        "Speed ballast (kn)", min_value=6.0, max_value=20.0,
        value=11.5, step=0.5,
        key="vessel_speed_ballast", disabled=_sim_locked,
    )

# ── 💰 Market Rates ───────────────────────────────────────────────────────────
st.sidebar.markdown("### 💰 Market Rates")

# Charter hire — with BHSI live fetch button
hire_col1, hire_col2 = st.sidebar.columns([3, 1])
with hire_col1:
    charter_hire = st.number_input(
        "Charter hire ($/day)",
        min_value=1000, max_value=100000,
        value=int(st.session_state.get("charter_hire_rate", 9000)),
        step=100, key="charter_hire_input",
        label_visibility="collapsed", disabled=_sim_locked,
    )
with hire_col2:
    bhsi_btn = st.button("🔄", key="bhsi_fetch_btn",
                         help="Fetch live BHSI rate")

if bhsi_btn:
    with st.spinner("Fetching BHSI..."):
        _bhsi = fetch_bhsi_rate()
    if _bhsi["success"]:
        st.session_state["charter_hire_rate"] = _bhsi["rate"]
        st.sidebar.success(f"BHSI: ${_bhsi['rate']:,}/day")
        st.rerun()
    else:
        st.sidebar.warning(f"BHSI fetch failed: {_bhsi['error']}")

st.sidebar.caption(f"Charter hire: ${charter_hire:,}/day | Source: BHSI")

# Bunker prices — with live fetch button
st.sidebar.markdown("**Bunker prices ($/MT)**")
bunk_col1, bunk_col2, bunk_col3 = st.sidebar.columns([2, 2, 1])
with bunk_col1:
    lsfo_price = st.number_input(
        "LSFO", min_value=100, max_value=2000,
        value=int(st.session_state.get("lsfo_price", 560)),
        step=5, key="lsfo_input",
        label_visibility="collapsed", disabled=_sim_locked,
    )
    st.sidebar.caption("LSFO")
with bunk_col2:
    mgo_price = st.number_input(
        "MGO", min_value=100, max_value=2500,
        value=int(st.session_state.get("mgo_price", 780)),
        step=5, key="mgo_input",
        label_visibility="collapsed", disabled=_sim_locked,
    )
    st.sidebar.caption("MGO")
with bunk_col3:
    bunker_btn = st.button("🔄", key="bunker_fetch_btn",
                           help="Fetch live bunker prices — Singapore")

if bunker_btn:
    with st.spinner("Fetching bunker prices..."):
        _bunk = fetch_bunker_prices()
    if _bunk["success"]:
        if "lsfo" in _bunk:
            st.session_state["lsfo_price"] = _bunk["lsfo"]
        if "mgo" in _bunk:
            st.session_state["mgo_price"] = _bunk["mgo"]
        st.sidebar.success(
            f"Updated: LSFO ${_bunk.get('lsfo','?')} | MGO ${_bunk.get('mgo','?')}"
        )
        st.rerun()
    else:
        st.sidebar.warning(f"Bunker fetch failed: {_bunk['error']}")

# Remaining cost parameters (kept as-is)
st.sidebar.markdown("## 💰 Other Costs")
insurance_annual  = st.sidebar.number_input("Insurance (USD/year)",   value=16000, min_value=5000,  max_value=100000, step=1000, disabled=_sim_locked)
brokerage_pct_ui  = st.sidebar.number_input("Brokerage (%)",          value=3.75,  min_value=0.0,   max_value=10.0,   step=0.25, disabled=_sim_locked)
operating_days    = st.sidebar.number_input("Operating Days/Year",     value=330,   min_value=270,   max_value=365,    step=5,    disabled=_sim_locked)

st.sidebar.markdown("## 🏗️ Port Cost Settings")
fio_cargo    = st.sidebar.checkbox("FIO Cargo (Free In & Out — no stevedoring)", value=True,
                                    help="Uncheck to apply stevedoring charges per commodity rate",
                                    disabled=_sim_locked)
port_charge_vol = st.sidebar.slider("Port Charge Variation (±%)", 0, 30, 15, 5,
                                     help="Stochastic ±% variation applied to port navigation charges per iteration",
                                     disabled=_sim_locked) / 100.0
congestion_vol  = st.sidebar.slider("Congestion Variation (±%)", 0, 60, 40, 5,
                                     help="Stochastic ±% variation applied to waiting/congestion days per iteration",
                                     disabled=_sim_locked) / 100.0

with st.sidebar.expander("Port Charge Overrides (CSV)"):
    from data.port_charges import PORT_CHARGES, PORT_CHARGES_DEFAULT
    import io
    _pc_rows = []
    for pname, vals in PORT_CHARGES.items():
        _pc_rows.append({'Port': pname, 'Nav_USD': vals['nav'],
                         'Cong_Mean_Days': vals['cong_mean'], 'Cong_Std_Days': vals['cong_std']})
    _pc_df = pd.DataFrame(_pc_rows)
    _csv_bytes = _pc_df.to_csv(index=False).encode()
    st.download_button("Download Port Charges CSV", data=_csv_bytes,
                       file_name="port_charges_override.csv", mime="text/csv",
                       help="Edit and re-upload to override default port charges")
    _uploaded = st.file_uploader("Upload Modified CSV", type="csv", key="port_charge_upload")
    if _uploaded is not None:
        try:
            _override_df = pd.read_csv(_uploaded)
            _override_map = {row['Port']: {'nav': row['Nav_USD'],
                                            'cong_mean': row['Cong_Mean_Days'],
                                            'cong_std': row['Cong_Std_Days']}
                             for _, row in _override_df.iterrows()}
            PORT_CHARGES.update(_override_map)
            st.success(f"Loaded {len(_override_df)} port charge overrides.")
        except Exception as _e:
            st.error(f"Invalid CSV: {_e}")

st.sidebar.markdown("---")
st.sidebar.markdown("## 🚀 Simulation")

algo_choice = st.sidebar.selectbox(
    "Algorithm",
    ["Hybrid (Greedy + Monte Carlo)", "Monte Carlo Only", "Greedy + Local Search"],
    index=1,
    key='algo_choice_sidebar',
    disabled=_sim_locked,
)
n_iterations = st.sidebar.selectbox(
    "Iterations",
    [1000, 5000, 10000, 25000, 50000],
    index=2,
    key='n_iterations_sidebar',
    disabled=_sim_locked,
)
dist_type = st.sidebar.radio(
    "Distribution type",
    ["Normal", "Triangular"],
    index=0,
    key='dist_type_sidebar',
    disabled=_sim_locked,
    help=(
        "Normal: symmetric, unbounded.\n"
        "Triangular: bounded by Min/Most Likely/Max — "
        "matches real observed market data ranges."
    )
)
_use_triangular = (dist_type == "Triangular")

if not _use_triangular:
    freight_vol = st.sidebar.slider(
        "Freight Rate Volatility (σ)", 0.05, 0.30, 0.15, 0.05,
        key='freight_vol_sidebar', disabled=_sim_locked,
    )
    bunker_vol = st.sidebar.slider(
        "Bunker Price Volatility (σ)", 0.05, 0.25, 0.10, 0.05,
        key='bunker_vol_sidebar', disabled=_sim_locked,
    )
    freight_min=0.70; freight_mode=1.00; freight_max=1.40
    bunker_min=0.75;  bunker_mode=1.00;  bunker_max=1.60
    cong_min=0.40;    cong_mode=1.00;    cong_max=2.00
else:
    freight_vol = 0.15
    bunker_vol  = 0.10
    st.sidebar.markdown(
        "<div style='font-size:11px;font-weight:600;color:#64748b;"
        "margin-top:4px;margin-bottom:2px'>Freight rate range</div>",
        unsafe_allow_html=True
    )
    _fc1, _fc2, _fc3 = st.sidebar.columns(3)
    freight_min  = _fc1.number_input("Min",  value=0.70,
        min_value=0.30, max_value=0.99, step=0.05,
        key='fr_min_sb', disabled=_sim_locked, format="%.2f")
    freight_mode = _fc2.number_input("Mode", value=1.00,
        min_value=0.50, max_value=1.50, step=0.05,
        key='fr_mode_sb', disabled=_sim_locked, format="%.2f")
    freight_max  = _fc3.number_input("Max",  value=1.40,
        min_value=1.01, max_value=2.50, step=0.05,
        key='fr_max_sb', disabled=_sim_locked, format="%.2f")

    st.sidebar.markdown(
        "<div style='font-size:11px;font-weight:600;color:#64748b;"
        "margin-top:4px;margin-bottom:2px'>Bunker price range</div>",
        unsafe_allow_html=True
    )
    _bc1, _bc2, _bc3 = st.sidebar.columns(3)
    bunker_min   = _bc1.number_input("Min",  value=0.75,
        min_value=0.30, max_value=0.99, step=0.05,
        key='bk_min_sb', disabled=_sim_locked, format="%.2f")
    bunker_mode  = _bc2.number_input("Mode", value=1.00,
        min_value=0.50, max_value=1.50, step=0.05,
        key='bk_mode_sb', disabled=_sim_locked, format="%.2f")
    bunker_max   = _bc3.number_input("Max",  value=1.60,
        min_value=1.01, max_value=3.00, step=0.05,
        key='bk_max_sb', disabled=_sim_locked, format="%.2f")

    st.sidebar.markdown(
        "<div style='font-size:11px;font-weight:600;color:#64748b;"
        "margin-top:4px;margin-bottom:2px'>Congestion range</div>",
        unsafe_allow_html=True
    )
    _cc1, _cc2, _cc3 = st.sidebar.columns(3)
    cong_min     = _cc1.number_input("Min",  value=0.40,
        min_value=0.10, max_value=0.99, step=0.10,
        key='cg_min_sb', disabled=_sim_locked, format="%.2f")
    cong_mode    = _cc2.number_input("Mode", value=1.00,
        min_value=0.50, max_value=2.00, step=0.10,
        key='cg_mode_sb', disabled=_sim_locked, format="%.2f")
    cong_max     = _cc3.number_input("Max",  value=2.00,
        min_value=1.01, max_value=5.00, step=0.10,
        key='cg_max_sb', disabled=_sim_locked, format="%.2f")

    st.sidebar.markdown(
        f"<div style='font-size:10px;color:#64748b;margin-top:4px;"
        f"background:#f8fafc;padding:5px 8px;border-radius:6px'>"
        f"Freight: {freight_min:.2f}→<b>{freight_mode:.2f}</b>"
        f"→{freight_max:.2f} · "
        f"Bunker: {bunker_min:.2f}→<b>{bunker_mode:.2f}</b>"
        f"→{bunker_max:.2f}</div>",
        unsafe_allow_html=True
    )

st.sidebar.markdown(
    "<div style='font-size:11px;font-weight:600;color:#64748b;"
    "margin-top:8px;margin-bottom:2px'>Reproducibility</div>",
    unsafe_allow_html=True
)
fixed_seed_on = st.sidebar.checkbox(
    "Fixed seed (reproducible results)",
    value=False,
    key="fixed_seed_checkbox",
    disabled=_sim_locked,
)
if fixed_seed_on:
    seed_value = st.sidebar.number_input(
        "Seed number", min_value=0, max_value=999999, value=42,
        step=1, key="fixed_seed_value", disabled=_sim_locked,
    )
    st.sidebar.caption("Fixed seed: results will be identical each run.")
else:
    seed_value = None
    st.sidebar.caption("Random seed: each run explores different programmes.")

st.sidebar.markdown("<br>", unsafe_allow_html=True)
if _sim_locked:
    st.sidebar.markdown(
        "<div style='background:linear-gradient(135deg,#f59e0b22,#f59e0b44);"
        "border-left:4px solid #f59e0b;padding:10px 14px;border-radius:8px;"
        "font-size:0.85rem;color:#92400e;font-weight:600'>"
        "⏳ Simulation running...<br>"
        "<span style='font-weight:400;font-size:0.78rem'>"
        "Controls locked until complete</span>"
        "</div>",
        unsafe_allow_html=True
    )
    run_simulation_clicked = False
else:
    run_simulation_clicked = st.sidebar.button(
        "🚀 Run Simulation",
        type="primary",
        use_container_width=True,
        key='run_sim_sidebar_btn',
    )

_algo_map = {
    "Hybrid (Greedy + Monte Carlo)": "hybrid",
    "Monte Carlo Only": "monte_carlo",
    "Greedy + Local Search": "greedy",
}

# ─── DATA PATH ───────────────────────────────────────────────────────────────
DATA_PATH = os.path.join(os.path.dirname(__file__), 'data', 'D1_Port_Pair_Matrix_Advantis.xlsx')

# ── Post-simulation success banner ───────────────────────────────────────────
if st.session_state.get('sim_done') and 'analysis' in st.session_state:
    _res_done = st.session_state['results']
    _el_done  = st.session_state.get('elapsed', 0)
    _its_done = len(_res_done)
    _ips_done = _its_done / max(_el_done, 0.001)
    st.success(
        f"✅ Simulation complete — {_its_done:,} iterations in "
        f"{_el_done:.1f}s ({_ips_done:.0f} iter/sec)  |  "
        f"Best profit: ${max(r['total_profit'] for r in _res_done):,.0f}  |  "
        f"Navigate to any tab above to explore results."
    )

tabs = st.tabs([
    "🌏 Network & Data",
    "📈 Summary Results",
    "⚙️ What-If Editor",
    "📉 Sensitivity",
    "🗺️ Voyage Analysis",
    "🚢 Voyage Journey",
    "⚓ Port Validation",
])

# ─── TAB 1: NETWORK & DATA (merged) ──────────────────────────────────────────
with tabs[0]:
    if os.path.exists(DATA_PATH):
        with st.spinner("Loading data..."):
            intra, ports, dist_matrix, legs = load_data(DATA_PATH)

        # ── Sea distance matrix status ────────────────────────────────────
        try:
            from data.sea_distances_loader import _DISTANCE_MATRIX, is_loaded as _sea_is_loaded
            if _sea_is_loaded():
                _n_ports_sea = len(_DISTANCE_MATRIX)
                _n_routes_sea = sum(len(v) for v in _DISTANCE_MATRIX.values())
                st.success(
                    f"Real sea distance matrix loaded — "
                    f"{_n_ports_sea} ports, {_n_routes_sea:,} routes "
                    f"(searoute EU maritime routing network)"
                )
            else:
                st.warning(
                    "Sea distance matrix not found — using Haversine approximation. "
                    "Run `python data/build_distance_matrix.py` to build it (one-time, ~10 min)."
                )
        except ImportError:
            pass

        # ── Top metrics row ───────────────────────────────────────────────
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Ports in Network",   len(ports))
        m2.metric("Feasible Voyage Legs", f"{len(legs):,}")
        m3.metric("Observed Routes",
                  f"{len(legs[legs['status']=='observed']):,}")
        m4.metric("Plausible Routes",
                  f"{len(legs[legs['status']=='plausible']):,}")

        st.markdown("---")

        # ── Side by side: Map LEFT, Data RIGHT ───────────────────────────
        col_map, col_data = st.columns([3, 2], gap="large")

        with col_map:
            st.markdown("### Port Network Map")
            fig_net = px.scatter_map(
                ports, lat='Lat', lon='Lon', size='Total_Vol',
                color='Country', hover_name='Port',
                hover_data={
                    'Load_Vol': ':.0f',
                    'Disch_Vol': ':.0f',
                    'Total_Vol': ':.0f'
                },
                map_style="carto-positron",
                zoom=3, center={"lat": 5, "lon": 115},
                size_max=30,
            )
            fig_net.update_layout(height=500, margin=dict(l=0,r=0,t=0,b=0))
            st.plotly_chart(fig_net, use_container_width=True)

            with st.expander("Distance Matrix Heatmap (Top 20 Ports)"):
                top20_idx   = ports.head(20).index.tolist()
                top20_names = ports.head(20)['Port'].tolist()
                sub_dist    = dist_matrix[np.ix_(top20_idx, top20_idx)]
                fig_dist = px.imshow(
                    sub_dist, x=top20_names, y=top20_names,
                    color_continuous_scale='Blues',
                    title="Sea Distance (NM) — Top 20 Ports"
                )
                fig_dist.update_layout(height=500)
                st.plotly_chart(fig_dist, use_container_width=True)

        with col_data:
            st.markdown("### Port Database")
            disp = ports[[
                'Port_ID', 'Port', 'Country',
                'Load_Vol', 'Disch_Vol', 'Total_Vol', 'Lat', 'Lon'
            ]].copy()
            disp['Load_Vol']  = (disp['Load_Vol']  / 1e6).round(1)
            disp['Disch_Vol'] = (disp['Disch_Vol'] / 1e6).round(1)
            disp['Total_Vol'] = (disp['Total_Vol'] / 1e6).round(1)
            disp.columns = [
                'ID', 'Port', 'Country',
                'Load (M MT)', 'Disch (M MT)', 'Total (M MT)', 'Lat', 'Lon'
            ]
            st.dataframe(disp, use_container_width=True, height=280)

            st.markdown("### Legs by Commodity")
            comm_dist = legs.groupby('commodity').size().sort_values(ascending=True)
            fig_comm = px.bar(
                x=comm_dist.values, y=comm_dist.index,
                orientation='h',
                labels={'x': 'Count', 'y': 'Commodity'},
                color=comm_dist.values,
                color_continuous_scale='Blues',
            )
            fig_comm.update_layout(
                height=380,
                showlegend=False,
                coloraxis_showscale=False,
                margin=dict(l=0, r=0, t=0, b=0),
            )
            st.plotly_chart(fig_comm, use_container_width=True)

            st.markdown("### Legs by Origin Country")
            country_dist = legs.groupby('origin_country').size().sort_values(ascending=True)
            fig_cntry = px.bar(
                x=country_dist.values, y=country_dist.index,
                orientation='h',
                labels={'x': 'Count', 'y': 'Country'},
                color=country_dist.values,
                color_continuous_scale='Teal',
            )
            fig_cntry.update_layout(
                height=260,
                showlegend=False,
                coloraxis_showscale=False,
                margin=dict(l=0, r=0, t=0, b=0),
            )
            st.plotly_chart(fig_cntry, use_container_width=True)

        # ── Network Graph Analysis (full width below) ─────────────────────
        if HAS_NX:
            st.markdown("---")
            st.markdown("### Network Graph Analysis")
            with st.spinner("Building voyage graph..."):
                vessel_for_graph = VesselConfig(
                    dwt=dwt_val, dwcc=dwcc_val,
                    speed_laden_knots=speed_laden,
                    speed_ballast_knots=speed_ballast,
                    charter_hire_day=charter_hire,
                    lsfo_price_mt=lsfo_price,
                    mgo_price_mt=mgo_price,
                    insurance_annual=insurance_annual,
                    brokerage_pct=brokerage_pct_ui / 100.0,
                    operating_days_year=operating_days,
                )
                G           = build_voyage_graph(legs, vessel_for_graph)
                centrality  = compute_port_centrality(G)
                communities = find_communities(G)

            if G is not None:
                cent_df = pd.DataFrame([
                    {
                        'Port':       p,
                        'Centrality': round(c, 4),
                        'Community':  communities.get(p, 0)
                    }
                    for p, c in sorted(
                        centrality.items(), key=lambda x: -x[1]
                    )[:30]
                ])
                gc1, gc2 = st.columns(2)
                with gc1:
                    st.markdown("**Top 30 Hub Ports by Betweenness Centrality**")
                    st.dataframe(cent_df, use_container_width=True, height=500)
                with gc2:
                    fig_cent = px.bar(
                        cent_df, x='Centrality', y='Port',
                        orientation='h', color='Community',
                        title="Port Network Centrality",
                        labels={
                            'Centrality': 'Betweenness Centrality',
                            'Port': ''
                        }
                    )
                    fig_cent.update_layout(
                        height=600,
                        yaxis={'categoryorder': 'total ascending'}
                    )
                    st.plotly_chart(fig_cent, use_container_width=True)

                n_communities = len(set(communities.values()))
                st.info(
                    f"Detected **{n_communities} route communities** via "
                    f"greedy modularity detection. "
                    f"Graph: {G.number_of_nodes()} nodes, "
                    f"{G.number_of_edges()} edges."
                )
        else:
            st.warning(
                "Install networkx (`pip install networkx`) "
                "to enable graph analysis."
            )
    else:
        st.error(f"Data file not found: {DATA_PATH}")

# ─── TAB 4: SUMMARY RESULTS ──────────────────────────────────────────────────
with tabs[1]:
    if 'analysis' in st.session_state:
        analysis = st.session_state['analysis']
        s = analysis['summary']

        # ── Port → Country lookup for Sankey ─────────────────────────────────
        try:
            _intra_s, _ports_s, _, _ = load_data(DATA_PATH)
            port_country_map = dict(zip(_ports_s['Port'], _ports_s['Country']))
        except Exception:
            port_country_map = {}

        # ── Hero KPI cards ────────────────────────────────────────────────────
        st.markdown("""
<style>
.kpi-row { display:flex; gap:12px; margin-bottom:1.5rem; flex-wrap:wrap; }
.kpi-card {
    flex:1; min-width:140px; padding:16px 20px;
    background:linear-gradient(135deg,#1a3a5c 0%,#2d5986 100%);
    border-radius:12px; color:white;
}
.kpi-val  { font-size:1.7rem; font-weight:700; letter-spacing:-0.5px; }
.kpi-lbl  { font-size:0.78rem; opacity:0.75; margin-top:4px; }
.kpi-del  { font-size:0.82rem; margin-top:6px; }
.kpi-pos  { color:#86efac; }
.kpi-neg  { color:#fca5a5; }
</style>
""", unsafe_allow_html=True)

        results = st.session_state['results']
        pct_above_market = (
            sum(1 for r in results if r['avg_tce'] >= 8500) / max(len(results), 1) * 100
        )
        # VaR colour — red if negative, amber if within 20% of zero
        _var_val  = s['var_profit']
        _var_col  = ('kpi-neg' if _var_val < 0
                     else 'kpi-pos' if _var_val > s['mean_profit'] * 0.3
                     else '')
        _loss_pct = s.get('loss_pct', 100 - s['profitable_pct'])

        st.markdown(f"""
<div class="kpi-row">
  <div class="kpi-card">
    <div class="kpi-val">${s['mean_profit']:,.0f}</div>
    <div class="kpi-lbl">Mean Annual Profit</div>
    <div class="kpi-del kpi-{'pos' if s['mean_profit']>0 else 'neg'}">
      P90: ${s['p90_profit']:,.0f}
    </div>
  </div>
  <div class="kpi-card">
    <div class="kpi-val">${s['median_tce']:,.0f}</div>
    <div class="kpi-lbl">Median TCE ($/day)</div>
    <div class="kpi-del">Market avg ~$8,500</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-val">{s['profitable_pct']:.1f}%</div>
    <div class="kpi-lbl">Programmes Profitable</div>
    <div class="kpi-del kpi-neg">{_loss_pct:.1f}% loss-making</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-val">${s['p10_profit']:,.0f}</div>
    <div class="kpi-lbl">Downside P10</div>
    <div class="kpi-del">Worst 10% scenario</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-val kpi-{_var_col}">${_var_val:,.0f}</div>
    <div class="kpi-lbl">Value at Risk (P5)</div>
    <div class="kpi-del">Worst 5% scenario</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-val" style="color:#fbbf24">{analysis['top_programmes'][0].get('ballast_ratio', 0)*100:.0f}%</div>
    <div class="kpi-lbl">Ballast Ratio (best prog)</div>
    <div class="kpi-del" style="color:#fca5a5">-${analysis['top_programmes'][0].get('ballast_cost_total', 0):,.0f} empty cost</div>
  </div>
</div>
""", unsafe_allow_html=True)

        # ── Extended statistics panel ─────────────────────────────────
        with st.expander("📊 Full Statistical Summary", expanded=False):
            _sc1, _sc2, _sc3 = st.columns(3)

            with _sc1:
                st.markdown(
                    "<div style='font-size:11px;font-weight:600;"
                    "color:#64748b;text-transform:uppercase;"
                    "letter-spacing:.05em;margin-bottom:8px'>"
                    "Central Tendency</div>",
                    unsafe_allow_html=True
                )
                _stats_left = [
                    ("Mean profit",   f"${s['mean_profit']:,.0f}"),
                    ("Median profit", f"${s['median_profit']:,.0f}"),
                    ("Std deviation", f"${s['std_profit']:,.0f}"),
                    ("Std error",     f"${s.get('stderr_profit',0):,.0f}"),
                ]
                for _lbl, _val in _stats_left:
                    st.markdown(
                        f"<div style='display:flex;justify-content:"
                        f"space-between;font-size:11px;padding:4px 0;"
                        f"border-bottom:0.5px solid #e2e8f0'>"
                        f"<span style='color:#64748b'>{_lbl}</span>"
                        f"<span style='font-weight:500;color:#1a3a5c'>"
                        f"{_val}</span></div>",
                        unsafe_allow_html=True
                    )

            with _sc2:
                st.markdown(
                    "<div style='font-size:11px;font-weight:600;"
                    "color:#64748b;text-transform:uppercase;"
                    "letter-spacing:.05em;margin-bottom:8px'>"
                    "Confidence Intervals (on mean)</div>",
                    unsafe_allow_html=True
                )
                _ci95_l = s.get('ci95_low',  s['mean_profit'])
                _ci95_h = s.get('ci95_high', s['mean_profit'])
                _ci90_l = s.get('ci90_low',  s['mean_profit'])
                _ci90_h = s.get('ci90_high', s['mean_profit'])
                _stats_mid = [
                    ("95% CI lower", f"${_ci95_l:,.0f}"),
                    ("95% CI upper", f"${_ci95_h:,.0f}"),
                    ("90% CI lower", f"${_ci90_l:,.0f}"),
                    ("90% CI upper", f"${_ci90_h:,.0f}"),
                ]
                for _lbl, _val in _stats_mid:
                    st.markdown(
                        f"<div style='display:flex;justify-content:"
                        f"space-between;font-size:11px;padding:4px 0;"
                        f"border-bottom:0.5px solid #e2e8f0'>"
                        f"<span style='color:#64748b'>{_lbl}</span>"
                        f"<span style='font-weight:500;color:#1a3a5c'>"
                        f"{_val}</span></div>",
                        unsafe_allow_html=True
                    )

            with _sc3:
                st.markdown(
                    "<div style='font-size:11px;font-weight:600;"
                    "color:#64748b;text-transform:uppercase;"
                    "letter-spacing:.05em;margin-bottom:8px'>"
                    "Risk Metrics</div>",
                    unsafe_allow_html=True
                )
                _var = s.get('var_profit', s['p10_profit'])
                _loss_p = s.get('loss_pct', 100 - s['profitable_pct'])
                _stats_right = [
                    ("Value at Risk (P5)", f"${_var:,.0f}"),
                    ("P10 downside",       f"${s['p10_profit']:,.0f}"),
                    ("P25",                f"${s['p25_profit']:,.0f}"),
                    ("P75",                f"${s['p75_profit']:,.0f}"),
                    ("P90 upside",         f"${s['p90_profit']:,.0f}"),
                    ("% loss-making",      f"{_loss_p:.1f}%"),
                ]
                for _lbl, _val in _stats_right:
                    _is_risk = 'Risk' in _lbl or 'P10' in _lbl or 'loss' in _lbl
                    _vc = '#991b1b' if (_is_risk and _var < 0) else '#1a3a5c'
                    st.markdown(
                        f"<div style='display:flex;justify-content:"
                        f"space-between;font-size:11px;padding:4px 0;"
                        f"border-bottom:0.5px solid #e2e8f0'>"
                        f"<span style='color:#64748b'>{_lbl}</span>"
                        f"<span style='font-weight:500;color:{_vc}'>"
                        f"{_val}</span></div>",
                        unsafe_allow_html=True
                    )

        st.markdown("### Profit Distribution")
        profits = [r['total_profit'] for r in results]
        tces    = [r['avg_tce'] for r in results]

        MARKET_TCE_BENCHMARKS = {
            'Break-even':        0,
            'Market floor':   5500,
            'SEA market avg': 8500,
            'Strong market': 12000,
            'Excellent':     16000,
        }

        col_dist1, col_dist2 = st.columns(2)
        with col_dist1:
            fig_profit = go.Figure()
            fig_profit.add_trace(go.Histogram(
                x=profits, nbinsx=80, marker_color='#667eea',
                name='Annual Profit', opacity=0.8
            ))
            fig_profit.add_vline(
                x=0, line_dash="dash", line_color="red",
                annotation_text="Break-even", annotation_position="top right"
            )
            fig_profit.add_vline(
                x=s['mean_profit'], line_dash="dot", line_color="#22c55e",
                annotation_text=f"Mean ${s['mean_profit']:,.0f}",
                annotation_position="top left"
            )
            fig_profit.update_layout(
                title="Annual Profit Distribution",
                xaxis_title="USD", height=380
            )
            st.plotly_chart(fig_profit, use_container_width=True)

        with col_dist2:
            fig_tce = go.Figure()
            fig_tce.add_trace(go.Histogram(
                x=tces, nbinsx=80, marker_color='#764ba2',
                name='TCE', opacity=0.8
            ))
            for label, value in MARKET_TCE_BENCHMARKS.items():
                color = 'red' if value == 0 else '#f59e0b' if value <= 8500 else '#22c55e'
                fig_tce.add_vline(
                    x=value, line_dash="dash", line_color=color,
                    annotation_text=f"{label} (${value:,})",
                    annotation_position="top right",
                    annotation_font_size=10,
                )
            fig_tce.update_layout(
                title="TCE Distribution vs Market Benchmarks",
                xaxis_title="USD/day", height=380
            )
            st.plotly_chart(fig_tce, use_container_width=True)

        mean_tce = s['median_tce']
        if mean_tce >= 12000:
            tce_verdict = "🟢 Excellent — well above SEA market average"
        elif mean_tce >= 8500:
            tce_verdict = "🟡 Good — at or above SEA market average"
        elif mean_tce >= 5500:
            tce_verdict = "🟠 Below average — but covering costs"
        else:
            tce_verdict = "🔴 Poor — below typical market floor"
        st.info(
            f"**Median TCE: ${mean_tce:,.0f}/day** — {tce_verdict}  |  "
            f"SEA ~20k DWT handy bulk market reference: $8,500–$12,000/day"
        )

        col1, col2 = st.columns(2)
        with col1:
            port_df = pd.DataFrame(analysis['port_ranking'][:30])
            if len(port_df) > 0:
                fig = px.bar(port_df, x='frequency_pct', y='port', orientation='h',
                             title="Port Frequency in Top 10% Programmes",
                             labels={'frequency_pct': 'Appearance %', 'port': 'Port'})
                fig.update_layout(height=700, yaxis={'categoryorder': 'total ascending'})
                st.plotly_chart(fig, use_container_width=True)
        with col2:
            comm_df = pd.DataFrame(analysis['commodity_ranking'])
            if len(comm_df) > 0:
                fig = px.bar(comm_df, x='avg_profit_per_leg', y='commodity', orientation='h',
                             title="Average Profit per Voyage Leg by Commodity",
                             labels={'avg_profit_per_leg': 'Avg Profit/Leg (USD)', 'commodity': 'Commodity'})
                fig.update_layout(height=700, yaxis={'categoryorder': 'total ascending'})
                st.plotly_chart(fig, use_container_width=True)

        # Radar chart — commodity performance scorecard
        st.markdown("#### Commodity Performance Scorecard")
        st.caption(
            "Each axis scored 0–10 relative to other commodities. "
            "Larger area = better overall performer."
        )

        comm_df_full = pd.DataFrame(analysis['commodity_ranking'])
        if len(comm_df_full) > 0:
            top_comms = comm_df_full.head(6)

            def normalise(series):
                mn, mx = series.min(), series.max()
                if mx == mn:
                    return pd.Series([5.0] * len(series), index=series.index)
                return (series - mn) / (mx - mn) * 10

            scores = pd.DataFrame()
            scores['commodity']     = top_comms['commodity'].values
            scores['Profitability'] = normalise(top_comms['avg_profit_per_leg']).values
            scores['Frequency']     = normalise(top_comms['frequency']).values
            scores['Total Revenue'] = normalise(top_comms['total_revenue']).values
            scores['Total Profit']  = normalise(top_comms['total_profit']).values
            scores['Consistency']   = normalise(
                top_comms['avg_profit_per_leg'] / (
                    top_comms['total_profit'].abs() /
                    top_comms['frequency'].clip(lower=1)
                ).clip(lower=0.1)).values

            categories = ['Profitability', 'Frequency',
                          'Total Revenue', 'Total Profit', 'Consistency']

            RADAR_COLORS = [
                '#667eea', '#22c55e', '#f59e0b',
                '#ef4444', '#06b6d4', '#8b5cf6'
            ]

            fig_radar = go.Figure()
            for i, row in scores.iterrows():
                vals = [row[c] for c in categories]
                vals_closed = vals + [vals[0]]
                cats_closed = categories + [categories[0]]
                fig_radar.add_trace(go.Scatterpolar(
                    r=vals_closed,
                    theta=cats_closed,
                    fill='toself',
                    name=row['commodity'],
                    line=dict(color=RADAR_COLORS[i % len(RADAR_COLORS)], width=2),
                    fillcolor=RADAR_COLORS[i % len(RADAR_COLORS)],
                    opacity=0.15,
                    hovertemplate=(
                        f"<b>{row['commodity']}</b><br>"
                        + "<br>".join(
                            f"{c}: {row[c]:.1f}/10" for c in categories
                        )
                        + "<extra></extra>"
                    ),
                ))

            fig_radar.update_layout(
                polar=dict(
                    radialaxis=dict(
                        visible=True,
                        range=[0, 10],
                        tickfont=dict(size=9),
                        gridcolor='rgba(0,0,0,0.1)',
                    ),
                    angularaxis=dict(
                        tickfont=dict(size=11, color='#1a3a5c'),
                        gridcolor='rgba(0,0,0,0.1)',
                    ),
                    bgcolor='rgba(0,0,0,0)',
                ),
                showlegend=True,
                legend=dict(
                    orientation='v',
                    x=1.05, y=0.5,
                    font=dict(size=11),
                ),
                title=dict(
                    text="Top 6 Commodities — Multi-Dimension Performance",
                    font=dict(size=13, color='#1a3a5c'),
                ),
                height=480,
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                margin=dict(l=60, r=160, t=60, b=40),
            )
            st.plotly_chart(fig_radar, use_container_width=True)

        route_df = pd.DataFrame(analysis['route_ranking'][:25])
        if len(route_df) > 0:
            fig = px.bar(route_df, x='avg_profit', y='route', orientation='h',
                         title="Top 25 Routes by Average Profit",
                         labels={'avg_profit': 'Avg Profit (USD)', 'route': 'Route'},
                         color='frequency', color_continuous_scale='Viridis')
            fig.update_layout(height=700, yaxis={'categoryorder': 'total ascending'})
            st.plotly_chart(fig, use_container_width=True)

        net_df = pd.DataFrame(analysis['network_size'])
        if len(net_df) > 0:
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            fig.add_trace(go.Bar(x=net_df['n_ports'], y=net_df['mean_profit'],
                                 name='Mean Profit', marker_color='#667eea'), secondary_y=False)
            fig.add_trace(go.Scatter(x=net_df['n_ports'], y=net_df['mean_tce'],
                                     name='Mean TCE', line=dict(color='red', width=3)), secondary_y=True)
            fig.update_layout(title="Profit & TCE by Ports in Network", xaxis_title="Number of Ports", height=420)
            fig.update_yaxes(title_text="Mean Profit (USD)", secondary_y=False)
            fig.update_yaxes(title_text="Mean TCE (USD/day)", secondary_y=True)
            st.plotly_chart(fig, use_container_width=True)

        phase_df = pd.DataFrame(analysis['phase_comparison'])
        if len(phase_df) > 0:
            phase_label = {0: 'Greedy', 1: 'Exploration', 2: 'Informed', 3: 'Exploitation'}
            phase_df['phase_name'] = phase_df['phase'].map(phase_label).fillna('Unknown')
            fig = px.bar(phase_df, x='phase_name', y=['mean_profit', 'median_profit', 'max_profit'],
                         barmode='group', title="Profit by Simulation Phase")
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)

        # ── Diagnostic log viewer ─────────────────────────────────────────
        st.markdown("---")
        _log_txt = st.session_state.get('sim_log', '')
        _log_pth = st.session_state.get('sim_log_path', '')
        with st.expander("📋 View Simulation Log", expanded=False):
            if _log_txt:
                if _log_pth:
                    st.caption(f"Log file: `{_log_pth}`")
                st.code(_log_txt, language=None)
                st.download_button(
                    label="⬇️ Download simulation_log.txt",
                    data=_log_txt,
                    file_name="simulation_log.txt",
                    mime="text/plain",
                )
            else:
                st.info("No log available — run the simulation to generate a log.")

        # ── Cargo Flow Sankey ─────────────────────────────────────────────
        st.markdown("---")
        st.markdown(
            "<div style='font-size:13px;font-weight:600;color:#1a3a5c;"
            "margin-bottom:8px'>🌊 Cargo Flow — Trade Pattern Analysis</div>"
            "<div style='font-size:11px;color:#64748b;margin-bottom:12px'>"
            "Flow width = number of voyages. Shows which trade lanes the "
            "simulation discovers as most valuable.</div>",
            unsafe_allow_html=True
        )

        # Build Sankey data from top 20 programmes
        top_progs_sankey = analysis['top_programmes'][:20]
        flow_counts = {}

        for prog in top_progs_sankey:
            for leg in prog.get('legs', []):
                orig = leg.get('origin_port', '')
                dest = leg.get('dest_port', '')
                comm = leg.get('commodity', '')

                orig_country = port_country_map.get(orig, orig[:8])
                dest_country = port_country_map.get(dest, dest[:8])

                if orig_country and dest_country and orig_country != dest_country:
                    key = (orig_country, dest_country, comm)
                    flow_counts[key] = flow_counts.get(key, 0) + 1

        if flow_counts:
            all_nodes = []
            node_map  = {}

            for (orig_c, dest_c, comm), count in flow_counts.items():
                src_label = f"{orig_c} (Load)"
                dst_label = f"{dest_c} (Disch)"
                if src_label not in node_map:
                    node_map[src_label] = len(all_nodes)
                    all_nodes.append(src_label)
                if dst_label not in node_map:
                    node_map[dst_label] = len(all_nodes)
                    all_nodes.append(dst_label)

            links_agg = {}
            for (orig_c, dest_c, comm), count in flow_counts.items():
                src_label = f"{orig_c} (Load)"
                dst_label = f"{dest_c} (Disch)"
                lkey = (node_map[src_label], node_map[dst_label], comm)
                links_agg[lkey] = links_agg.get(lkey, 0) + count

            COMM_COLORS = {
                'Steam Coal':           'rgba(71,85,105,0.6)',
                'Coking Coal':          'rgba(51,65,85,0.6)',
                'Nickel Ore':           'rgba(180,83,9,0.6)',
                'Palm Kernel Expeller': 'rgba(22,163,74,0.6)',
                'Sugar':                'rgba(234,179,8,0.6)',
                'Steels':               'rgba(59,130,246,0.6)',
                'Fertilizers':          'rgba(168,85,247,0.6)',
                'Clinker':              'rgba(239,68,68,0.6)',
                'Grain':                'rgba(16,185,129,0.6)',
            }

            sources = [lk[0] for lk in links_agg]
            targets = [lk[1] for lk in links_agg]
            values  = [v for v in links_agg.values()]
            colors  = [COMM_COLORS.get(lk[2], 'rgba(100,116,139,0.5)')
                       for lk in links_agg]
            labels_hover = [lk[2] for lk in links_agg]

            NODE_COLORS = []
            for node in all_nodes:
                if '(Load)' in node:
                    NODE_COLORS.append('#1a3a5c')
                else:
                    NODE_COLORS.append('#166534')

            fig_sankey = go.Figure(go.Sankey(
                arrangement='snap',
                node=dict(
                    pad=20,
                    thickness=20,
                    line=dict(color='white', width=0.5),
                    label=all_nodes,
                    color=NODE_COLORS,
                    hovertemplate='%{label}<extra></extra>',
                ),
                link=dict(
                    source=sources,
                    target=targets,
                    value=values,
                    color=colors,
                    customdata=labels_hover,
                    hovertemplate=(
                        '%{customdata}<br>'
                        'Voyages: %{value}<extra></extra>'
                    ),
                ),
            ))
            fig_sankey.update_layout(
                height=420,
                margin=dict(l=10, r=10, t=10, b=10),
                paper_bgcolor='rgba(0,0,0,0)',
                font=dict(size=11, color='#1e293b'),
            )
            st.plotly_chart(fig_sankey, use_container_width=True)

            # Commodity colour legend
            leg_cols = st.columns(len(COMM_COLORS))
            for i, (comm_name, color) in enumerate(COMM_COLORS.items()):
                if i < len(leg_cols):
                    rgb = color.replace('rgba(', '').replace(')', '').split(',')
                    hex_c = '#{:02x}{:02x}{:02x}'.format(
                        int(rgb[0]), int(rgb[1]), int(rgb[2])
                    )
                    leg_cols[i].markdown(
                        f"<div style='display:flex;align-items:center;gap:4px'>"
                        f"<div style='width:12px;height:12px;border-radius:2px;"
                        f"background:{hex_c}'></div>"
                        f"<span style='font-size:10px;color:#475569'>"
                        f"{comm_name}</span></div>",
                        unsafe_allow_html=True
                    )
        else:
            st.info("Run simulation to see cargo flow analysis.")

    else:
        st.info("Run the simulation first.")

# ─── TAB 6: WHAT-IF / VOYAGE EDITOR ─────────────────────────────────────────
with tabs[2]:
    if 'analysis' in st.session_state:
        analysis  = st.session_state['analysis']
        vessel    = st.session_state.get('vessel')
        dm        = st.session_state.get('dist_matrix')
        legs_df   = st.session_state.get('legs_df')
        top_progs = analysis['top_programmes']

        if vessel is None or dm is None or legs_df is None:
            st.warning("Re-run the simulation to enable the What-If editor.")
        else:
            st.markdown("### What-If / Voyage Editor")
            st.info(
                "Modify any voyage in a programme and all downstream voyages automatically "
                "cascade-recalculate (ballast distances, costs, cumulative profit)."
            )

            prog_sel = st.selectbox("Load programme", range(1, len(top_progs) + 1),
                                    key='whatif_prog')
            prog = top_progs[prog_sel - 1]

            # Build fast library once
            if 'fast_lib' not in st.session_state:
                from modules.simulation_engine import _ensure_port_cost_columns
                legs_df_v2 = _ensure_port_cost_columns(legs_df)
                st.session_state['fast_lib'] = FastLegLibrary(legs_df_v2, vessel)

            fast_lib = st.session_state['fast_lib']

            # Reconstruct VoyageLeg objects from dicts
            from modules.simulation_engine import VoyageLeg, cascade_recalculate_legs

            def dict_to_leg(d):
                leg = VoyageLeg(
                    origin_id=int(d.get('origin_id', 0)),
                    dest_id=int(d.get('dest_id', 0)),
                    origin_port=d['origin_port'],
                    dest_port=d['dest_port'],
                    ballast_from_port=d.get('ballast_from_port', ''),
                    commodity=d['commodity'],
                    category=d.get('category', ''),
                    cargo_mt=d.get('cargo_mt', vessel.dwcc),
                    freight_rate=d.get('freight_rate', 0),
                    ballast_nm=d.get('ballast_nm', d.get('ballast_distance_nm', 0)),
                    laden_nm=d.get('laden_nm', d.get('distance_nm', 0)),
                    gross_freight=d.get('gross_freight', d.get('revenue', 0)),
                    brokerage=d.get('brokerage', 0),
                    net_income=d.get('net_income', 0),
                    maneuver_days=d.get('maneuver_days', 0.503333),
                    loading_days=d.get('loading_days', d.get('load_days', 0)),
                    discharge_days=d.get('discharge_days', d.get('disch_days', 0)),
                    port_days=d.get('port_days', 0),
                    idle_days=d.get('idle_days', 0),
                    ballast_days=d.get('ballast_days', 0),
                    laden_days=d.get('laden_days', 0),
                    total_days=d.get('total_days', 0),
                    lsfo_mt=d.get('lsfo_mt', 0),
                    mgo_mt=d.get('mgo_mt', 0),
                    lsfo_cost=d.get('lsfo_cost', 0),
                    mgo_cost=d.get('mgo_cost', 0),
                    bunker_cost=d.get('bunker_cost', 0),
                    charter_hire=d.get('charter_hire', d.get('charter_hire_cost', 0)),
                    port_costs=d.get('port_costs', 0),
                    load_port_nav=d.get('load_port_nav', 0),
                    load_port_steve=d.get('load_port_steve', 0),
                    disch_port_nav=d.get('disch_port_nav', 0),
                    disch_port_steve=d.get('disch_port_steve', 0),
                    insurance=d.get('insurance', 0),
                    other_costs=d.get('other_costs', 1000),
                    total_expenses=d.get('total_expenses', d.get('total_cost', 0)),
                    profit_loss=d.get('profit_loss', d.get('profit', 0)),
                    profit_per_day=d.get('profit_per_day', 0),
                    profit_per_mt=d.get('profit_per_mt', 0),
                    cum_days=d.get('cum_days', 0),
                    cum_profit=d.get('cum_profit', 0),
                )
                return leg

            # Initialise session state for the working copy of legs
            prog_key = f'whatif_legs_{prog_sel}'
            if prog_key not in st.session_state:
                st.session_state[prog_key] = [dict_to_leg(d) for d in prog['legs']]

            working_legs = st.session_state[prog_key]

            # ── Voyage selector and editor ────────────────────────────────────
            st.markdown("#### Select a voyage to modify")
            voy_labels = [
                f"V{i+1}: {l.origin_port} → {l.dest_port} | {l.commodity} | ${l.profit_loss:,.0f}"
                for i, l in enumerate(working_legs)
            ]
            edit_idx = st.selectbox("Voyage to edit", range(len(working_legs)),
                                    format_func=lambda i: voy_labels[i], key='whatif_voy')

            sel_leg = working_legs[edit_idx]

            # Collect available load ports and discharge ports from leg library
            load_ports = sorted(legs_df['origin_port'].unique().tolist())
            disch_ports = sorted(legs_df['dest_port'].unique().tolist())
            commodities = sorted(legs_df['commodity'].unique().tolist())

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                new_load = st.selectbox("New Load Port",
                                        load_ports,
                                        index=load_ports.index(sel_leg.origin_port) if sel_leg.origin_port in load_ports else 0,
                                        key='wi_load')
            with col2:
                new_disch = st.selectbox("New Discharge Port",
                                         disch_ports,
                                         index=disch_ports.index(sel_leg.dest_port) if sel_leg.dest_port in disch_ports else 0,
                                         key='wi_disch')
            with col3:
                new_comm = st.selectbox("Commodity",
                                        commodities,
                                        index=commodities.index(sel_leg.commodity) if sel_leg.commodity in commodities else 0,
                                        key='wi_comm')
            with col4:
                new_rate = st.number_input("Freight Rate ($/MT)",
                                           value=float(round(sel_leg.freight_rate, 2)),
                                           min_value=1.0, max_value=200.0, step=0.5,
                                           key='wi_rate')

            if st.button("Apply Change & Cascade Recalculate", type="primary"):
                # Find matching leg in library
                load_row = legs_df[
                    (legs_df['origin_port'] == new_load) &
                    (legs_df['dest_port']   == new_disch) &
                    (legs_df['commodity']   == new_comm)
                ]
                if load_row.empty:
                    st.error(f"No feasible leg found for {new_load} → {new_disch} carrying {new_comm}.")
                else:
                    row = load_row.iloc[0]
                    new_leg_idx = int(row.name) if int(row.name) < len(fast_lib.origin_ids) else _find_leg_idx(
                        fast_lib, int(row['origin_id']), int(row['dest_id']), new_comm
                    )
                    # Determine ballast NM from previous voyage
                    if edit_idx == 0:
                        ballast_nm = 0.0
                        bfrom = new_load
                    else:
                        prev_dest_id = working_legs[edit_idx - 1].dest_id
                        ballast_nm = float(dm[prev_dest_id, int(row['origin_id'])])
                        bfrom = working_legs[edit_idx - 1].dest_port

                    new_leg = fast_lib.build_voyage_leg(
                        _find_leg_idx(fast_lib, int(row['origin_id']), int(row['dest_id']), new_comm),
                        ballast_nm, bfrom,
                        vessel.lsfo_price_mt, vessel.mgo_price_mt,
                        new_rate,
                    )
                    if new_leg is None:
                        st.error("Failed to compute costs for this leg.")
                    else:
                        working_legs[edit_idx] = new_leg
                        # Cascade from the next voyage
                        working_legs = cascade_recalculate_legs(
                            working_legs, edit_idx + 1, dm, vessel, fast_lib,
                            vessel.lsfo_price_mt, vessel.mgo_price_mt,
                        )
                        st.session_state[prog_key] = working_legs
                        st.success(f"Voyage {edit_idx+1} updated — all downstream voyages recalculated.")
                        st.rerun()

            if st.button("Reset to Original Programme"):
                if prog_key in st.session_state:
                    del st.session_state[prog_key]
                st.rerun()

            # ── Before/After comparison ───────────────────────────────────────
            st.markdown("#### Current Programme — Voyage Schedule")
            wi_rows = []
            for i, leg in enumerate(working_legs):
                orig_leg = prog['legs'][i] if i < len(prog['legs']) else {}
                orig_profit = orig_leg.get('profit_loss', orig_leg.get('profit', 0))
                curr_profit = leg.profit_loss
                delta = curr_profit - orig_profit
                wi_rows.append({
                    'Voy #':       i + 1,
                    'Load Port':   leg.origin_port,
                    'Disch Port':  leg.dest_port,
                    'Commodity':   leg.commodity,
                    'Rate $/MT':   f"${leg.freight_rate:.2f}",
                    'Ballast NM':  f"{leg.ballast_nm:,.0f}",
                    'Laden NM':    f"{leg.laden_nm:,.0f}",
                    'Total Days':  f"{leg.total_days:.2f}",
                    'Profit':      f"${curr_profit:,.0f}",
                    'vs Original': f"{'+'if delta>=0 else ''}{delta:,.0f}",
                    'Cum Profit':  f"${leg.cum_profit:,.0f}",
                })
            st.dataframe(pd.DataFrame(wi_rows), use_container_width=True)

            # Totals comparison
            orig_total = sum(l.get('profit_loss', l.get('profit', 0)) for l in prog['legs'])
            new_total  = sum(l.profit_loss for l in working_legs)
            delta_total = new_total - orig_total

            col1, col2, col3 = st.columns(3)
            col1.metric("Original Annual Profit", f"${orig_total:,.0f}")
            col2.metric("Modified Annual Profit",  f"${new_total:,.0f}")
            col3.metric("Change",                  f"${delta_total:+,.0f}",
                        delta_color="normal" if delta_total >= 0 else "inverse")

            # Cumulative profit before/after chart
            orig_cum, new_cum = [], []
            o_run, n_run = 0.0, 0.0
            n_show = max(len(prog['legs']), len(working_legs))
            for i in range(n_show):
                if i < len(prog['legs']):
                    o_run += prog['legs'][i].get('profit_loss', prog['legs'][i].get('profit', 0))
                if i < len(working_legs):
                    n_run += working_legs[i].profit_loss
                orig_cum.append(o_run)
                new_cum.append(n_run)

            fig = go.Figure()
            fig.add_trace(go.Scatter(x=list(range(1, n_show + 1)), y=orig_cum,
                                     name='Original', line=dict(color='#667eea', width=2, dash='dash')))
            fig.add_trace(go.Scatter(x=list(range(1, n_show + 1)), y=new_cum,
                                     name='Modified', line=dict(color='#22c55e', width=3)))
            fig.add_hline(y=0, line_dash='dash', line_color='red')
            fig.update_layout(
                xaxis_title="Voyage Number",
                yaxis_title="Cumulative Profit (USD)",
                title="Cumulative Profit: Original vs Modified",
                height=420,
            )
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Run the simulation first to use the What-If editor.")

# ─── TAB 7: SENSITIVITY ANALYSIS ─────────────────────────────────────────────
with tabs[3]:
    if 'analysis' not in st.session_state:
        st.info("Run the simulation first.")
    else:
        st.markdown("### Sensitivity Analysis")
        st.markdown(
            "Adjust the sliders to see how changes in market conditions "
            "affect the top programme's profitability — instantly."
        )

        analysis = st.session_state['analysis']
        vessel   = st.session_state.get('vessel')
        top_prog = analysis['top_programmes'][0] if analysis['top_programmes'] else None

        if top_prog is None or vessel is None:
            st.warning("No results available.")
        else:
            legs_base   = top_prog['legs']
            base_profit = top_prog['total_profit']
            base_tce    = top_prog['avg_tce']

            st.markdown("#### Market Scenario Sliders")
            col1, col2, col3 = st.columns(3)
            with col1:
                bunker_delta = st.slider(
                    "Bunker Price Change (%)",
                    min_value=-40, max_value=60, value=0, step=5,
                    help="±% change applied to both LSFO and MGO prices"
                )
            with col2:
                freight_delta = st.slider(
                    "Freight Rate Change (%)",
                    min_value=-40, max_value=40, value=0, step=5,
                    help="±% change applied to all freight rates"
                )
            with col3:
                hire_delta = st.slider(
                    "Charter Hire Change (%)",
                    min_value=-30, max_value=50, value=0, step=5,
                    help="±% change in daily charter hire rate"
                )

            def recalculate_sensitivity(legs, bunker_pct, freight_pct, hire_pct):
                """Recompute programme P&L with adjusted market parameters."""
                b_mult = 1 + bunker_pct / 100
                f_mult = 1 + freight_pct / 100
                h_mult = 1 + hire_pct / 100
                new_profit  = 0.0
                new_revenue = 0.0
                new_bunker  = 0.0
                new_hire    = 0.0
                for leg in legs:
                    gross = leg.get('gross_freight', leg.get('revenue', 0)) * f_mult
                    brok  = gross * (brokerage_pct_ui / 100.0)
                    ni    = gross - brok
                    bunk  = leg.get('bunker_cost', 0) * b_mult
                    hire  = leg.get('charter_hire', leg.get('charter_hire_cost', 0)) * h_mult
                    port  = leg.get('port_costs', 0)
                    ins   = leg.get('insurance', 0)
                    oth   = leg.get('other_costs', 1000)
                    exp   = hire + bunk + port + ins + oth
                    pl    = ni - exp
                    new_profit  += pl
                    new_revenue += gross
                    new_bunker  += bunk
                    new_hire    += hire
                return {
                    'profit': new_profit,
                    'revenue': new_revenue,
                    'bunker': new_bunker,
                    'hire': new_hire,
                }

            result       = recalculate_sensitivity(legs_base, bunker_delta, freight_delta, hire_delta)
            new_profit   = result['profit']
            profit_delta = new_profit - base_profit
            profit_delta_pct = (profit_delta / abs(base_profit)) * 100 if base_profit != 0 else 0
            total_days   = sum(l.get('total_days', 0) for l in legs_base)
            new_tce = (
                result['revenue'] * (1 - brokerage_pct_ui / 100.0)
                - result['bunker']
                - sum(l.get('port_costs', 0) for l in legs_base)
                - sum(l.get('insurance', 0) for l in legs_base)
                - sum(l.get('other_costs', 1000) for l in legs_base)
            ) / max(total_days, 1)

            st.markdown("#### Adjusted Programme KPIs")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Base Profit",     f"${base_profit:,.0f}")
            c2.metric("Adjusted Profit", f"${new_profit:,.0f}",
                      delta=f"${profit_delta:+,.0f} ({profit_delta_pct:+.1f}%)",
                      delta_color="normal" if profit_delta >= 0 else "inverse")
            c3.metric("Adjusted TCE",    f"${new_tce:,.0f}/day",
                      delta=f"${new_tce - base_tce:+,.0f}/day",
                      delta_color="normal" if new_tce >= base_tce else "inverse")
            c4.metric("Break-even?",
                      "✅ Profitable" if new_profit > 0 else "❌ Loss-making")

            # Tornado chart
            st.markdown("#### Tornado Chart — Single Variable Impact")
            test_ranges = {
                'Bunker +40%':              recalculate_sensitivity(legs_base,  40,   0,   0)['profit'],
                'Bunker -40%':              recalculate_sensitivity(legs_base, -40,   0,   0)['profit'],
                'Freight +20%':             recalculate_sensitivity(legs_base,   0,  20,   0)['profit'],
                'Freight -20%':             recalculate_sensitivity(legs_base,   0, -20,   0)['profit'],
                'Hire +30%':                recalculate_sensitivity(legs_base,   0,   0,  30)['profit'],
                'Hire -30%':                recalculate_sensitivity(legs_base,   0,   0, -30)['profit'],
                'Bunker +20%, Freight -10%':recalculate_sensitivity(legs_base,  20, -10,   0)['profit'],
            }
            tornado_df = pd.DataFrame([
                {
                    'Scenario': k,
                    'Profit': v,
                    'Delta': v - base_profit,
                    'Color': '#22c55e' if v >= base_profit else '#ef4444',
                }
                for k, v in test_ranges.items()
            ]).sort_values('Delta')

            fig_tornado = go.Figure()
            fig_tornado.add_trace(go.Bar(
                y=tornado_df['Scenario'],
                x=tornado_df['Delta'],
                orientation='h',
                marker_color=tornado_df['Color'].tolist(),
                text=[f"${v:,.0f}" for v in tornado_df['Profit']],
                textposition='outside',
            ))
            fig_tornado.add_vline(x=0, line_color='#1a3a5c', line_width=2)
            fig_tornado.update_layout(
                title="Profit impact of single-variable changes vs base case",
                xaxis_title="Change in Annual Profit (USD)",
                height=420,
                yaxis=dict(tickfont=dict(size=11)),
            )
            st.plotly_chart(fig_tornado, use_container_width=True)

            # Scenario comparison table
            st.markdown("#### Scenario Comparison Table")
            scenarios = {
                'Base case':             (0,   0,   0),
                'Bunker spike +30%':     (30,  0,   0),
                'Freight market -15%':   (0,  -15,  0),
                'Hire +20%':             (0,   0,  20),
                'Bull market (fr +20%)': (0,  20,   0),
                'Bear market':           (20, -20,  10),
                'Perfect storm':         (40, -20,  20),
                'Your current sliders':  (bunker_delta, freight_delta, hire_delta),
            }
            scen_rows = []
            for name, (b, f, h) in scenarios.items():
                r = recalculate_sensitivity(legs_base, b, f, h)
                scen_rows.append({
                    'Scenario':      name,
                    'Bunker Δ':      f"{b:+d}%",
                    'Freight Δ':     f"{f:+d}%",
                    'Hire Δ':        f"{h:+d}%",
                    'Annual Profit': f"${r['profit']:,.0f}",
                    'vs Base':       f"${r['profit'] - base_profit:+,.0f}",
                    'Profitable':    '✅' if r['profit'] > 0 else '❌',
                })
            st.dataframe(
                pd.DataFrame(scen_rows),
                use_container_width=True,
                hide_index=True,
                height=320,
            )

# ─── SIMULATION RUN (outside tabs — triggered from sidebar) ──────────────────
if run_simulation_clicked and os.path.exists(DATA_PATH):
    st.session_state['sim_running'] = True
    st.session_state['sim_done']    = False
    intra, ports, dist_matrix, legs = load_data(DATA_PATH)

    vessel = VesselConfig(
        dwt=dwt_val, dwcc=dwcc_val,
        speed_laden_knots=speed_laden,
        speed_ballast_knots=speed_ballast,
        charter_hire_day=charter_hire,
        lsfo_price_mt=lsfo_price,
        mgo_price_mt=mgo_price,
        insurance_annual=insurance_annual,
        brokerage_pct=brokerage_pct_ui / 100.0,
        operating_days_year=operating_days,
        fuel_laden_mt_day=13.5,
        fuel_ballast_mt_day=13.5,
        bunker_price_mt=lsfo_price,
        draft_laden=draft_laden,
        draft_ballast=draft_ballast,
        loa=float(loa_val),
        beam=float(beam_val),
    )
    sim_config = SimConfig(
        n_iterations=n_iterations,
        algorithm=_algo_map[algo_choice],
        freight_volatility=freight_vol,
        bunker_volatility=bunker_vol,
        random_seed=seed_value,
        dist_type='triangular' if _use_triangular else 'normal',
        freight_min=freight_min,   freight_mode=freight_mode,
        freight_max=freight_max,
        bunker_min=bunker_min,     bunker_mode=bunker_mode,
        bunker_max=bunker_max,
        cong_min=cong_min,         cong_mode=cong_mode,
        cong_max=cong_max,
    )

    # ── Modal overlay container ───────────────────────────────────────────
    overlay = st.empty()
    with overlay.container():
        st.markdown(
            "<h2 style='text-align:center;color:#1a3a5c;"
            "margin-bottom:0.25rem'>🚀 Simulation Running</h2>",
            unsafe_allow_html=True
        )
        st.markdown(
            f"<p style='text-align:center;color:#64748b;margin-top:0'>"
            f"Running {n_iterations:,} iterations — "
            f"{algo_choice}</p>",
            unsafe_allow_html=True
        )
        st.markdown("---")

        prog_col1, prog_col2, prog_col3, prog_col4 = st.columns(4)
        live_phase      = prog_col1.empty()
        live_best       = prog_col2.empty()
        live_tce        = prog_col3.empty()
        live_speed      = prog_col4.empty()
        progress_bar    = st.progress(0)
        live_status     = st.empty()
        live_chart_slot = st.empty()

        live_phase.markdown(
            "<div style='background:#f1f5f9;border-left:4px solid #94a3b8;"
            "padding:12px 16px;border-radius:8px'>"
            "<div style='font-size:0.75rem;color:#64748b'>Current Phase</div>"
            "<div style='font-size:1rem;font-weight:700;color:#475569;"
            "margin-top:4px'>⏳ Starting...</div>"
            "</div>",
            unsafe_allow_html=True
        )
        live_best.markdown(
            "<div style='background:#f1f5f9;border-left:4px solid #94a3b8;"
            "padding:12px 16px;border-radius:8px'>"
            "<div style='font-size:0.75rem;color:#64748b'>Best Profit Found</div>"
            "<div style='font-size:1.4rem;font-weight:700;color:#475569;"
            "margin-top:4px'>—</div>"
            "</div>",
            unsafe_allow_html=True
        )
        live_tce.markdown(
            "<div style='background:#f1f5f9;border-left:4px solid #94a3b8;"
            "padding:12px 16px;border-radius:8px'>"
            "<div style='font-size:0.75rem;color:#64748b'>Best TCE</div>"
            "<div style='font-size:1.4rem;font-weight:700;color:#475569;"
            "margin-top:4px'>—</div>"
            "</div>",
            unsafe_allow_html=True
        )
        live_speed.markdown(
            "<div style='background:#f1f5f9;border-left:4px solid #94a3b8;"
            "padding:12px 16px;border-radius:8px'>"
            "<div style='font-size:0.75rem;color:#64748b'>Speed</div>"
            "<div style='font-size:1.4rem;font-weight:700;color:#475569;"
            "margin-top:4px'>—</div>"
            "</div>",
            unsafe_allow_html=True
        )

        start_time           = time.time()
        _best_profit_history = []
        _best_profit_so_far  = [float('-inf')]
        _best_tce_so_far     = [0.0]
        _iter_count          = [0]

        PHASE_COLORS = {
            'Greedy + Local Search':             ('#1a3a5c', '🔵'),
            'Phase 1: Pure Exploration':         ('#f59e0b', '🟡'),
            'Phase 2: Informed Exploration':     ('#667eea', '🟣'),
            'Phase 3: Intensive Exploitation':   ('#22c55e', '🟢'),
            'Complete':                          ('#22c55e', '✅'),
        }

        def progress_callback(phase_name, current, total):
            pct       = current / max(1, total)
            elapsed   = time.time() - start_time
            iters_sec = current / max(elapsed, 0.001)
            eta       = (total - current) / max(iters_sec, 0.001)
            progress_bar.progress(pct)
            _iter_count[0] = current
            color, icon = PHASE_COLORS.get(phase_name, ('#667eea', '⚙️'))
            live_phase.markdown(
                f"<div style='background:linear-gradient("
                f"135deg,{color}22,{color}44);"
                f"border-left:4px solid {color};"
                f"padding:12px 16px;border-radius:8px'>"
                f"<div style='font-size:0.75rem;color:#64748b'>"
                f"Current Phase</div>"
                f"<div style='font-size:1rem;font-weight:700;"
                f"color:{color};margin-top:4px'>{icon} "
                f"{phase_name.replace('Phase 1: ','').replace('Phase 2: ','').replace('Phase 3: ','')}"
                f"</div>"
                f"<div style='font-size:0.78rem;color:#64748b;"
                f"margin-top:4px'>{current:,}/{total:,} "
                f"({pct*100:.0f}%)</div>"
                f"</div>",
                unsafe_allow_html=True
            )
            live_speed.markdown(
                f"<div style='background:linear-gradient("
                f"135deg,#f8fafc,#e2e8f0);"
                f"padding:12px 16px;border-radius:8px'>"
                f"<div style='font-size:0.75rem;color:#64748b'>"
                f"Speed</div>"
                f"<div style='font-size:1.4rem;font-weight:700;"
                f"color:#1a3a5c;margin-top:4px'>{iters_sec:.0f}</div>"
                f"<div style='font-size:0.78rem;color:#64748b'>"
                f"iter/sec  |  ETA {eta:.0f}s</div>"
                f"</div>",
                unsafe_allow_html=True
            )
            live_status.markdown(
                f"<div style='text-align:center;color:#64748b;"
                f"font-size:0.82rem;padding:4px 0'>"
                f"Elapsed: {elapsed:.0f}s  |  "
                f"Iterations: {current:,}  |  "
                f"Remaining: {total - current:,}"
                f"</div>",
                unsafe_allow_html=True
            )

        def update_best_metrics(results_so_far):
            if not results_so_far:
                return
            best = max(results_so_far, key=lambda r: r['total_profit'])
            bp   = best['total_profit']
            bt   = best['avg_tce']
            if bp > _best_profit_so_far[0]:
                _best_profit_so_far[0] = bp
                _best_tce_so_far[0]    = bt
                _best_profit_history.append(bp)
                live_best.markdown(
                    f"<div style='background:linear-gradient("
                    f"135deg,#22c55e22,#22c55e44);"
                    f"border-left:4px solid #22c55e;"
                    f"padding:12px 16px;border-radius:8px'>"
                    f"<div style='font-size:0.75rem;color:#64748b'>"
                    f"Best Profit Found</div>"
                    f"<div style='font-size:1.4rem;font-weight:700;"
                    f"color:#166534;margin-top:4px'>${bp:,.0f}</div>"
                    f"<div style='font-size:0.78rem;color:#64748b;"
                    f"margin-top:4px'>After {_iter_count[0]:,} "
                    f"iterations</div>"
                    f"</div>",
                    unsafe_allow_html=True
                )
                live_tce.markdown(
                    f"<div style='background:linear-gradient("
                    f"135deg,#667eea22,#667eea44);"
                    f"border-left:4px solid #667eea;"
                    f"padding:12px 16px;border-radius:8px'>"
                    f"<div style='font-size:0.75rem;color:#64748b'>"
                    f"Best TCE</div>"
                    f"<div style='font-size:1.4rem;font-weight:700;"
                    f"color:#1a3a5c;margin-top:4px'>${bt:,.0f}/day</div>"
                    f"<div style='font-size:0.78rem;color:#64748b;"
                    f"margin-top:4px'>"
                    f"{'🟢 Above market' if bt >= 8500 else '🟡 Below market avg'}"
                    f"</div>"
                    f"</div>",
                    unsafe_allow_html=True
                )
                if len(_best_profit_history) >= 2:
                    fig_spark = go.Figure()
                    fig_spark.add_trace(go.Scatter(
                        x=list(range(len(_best_profit_history))),
                        y=_best_profit_history,
                        mode='lines',
                        fill='tozeroy',
                        line=dict(color='#22c55e', width=2),
                        fillcolor='rgba(34,197,94,0.15)',
                        showlegend=False,
                    ))
                    fig_spark.update_layout(
                        title=dict(
                            text="Best profit improving over simulation",
                            font=dict(size=11, color='#64748b')
                        ),
                        xaxis=dict(visible=False),
                        yaxis=dict(
                            tickformat='$,.0f',
                            tickfont=dict(size=9),
                            gridcolor='rgba(0,0,0,0.05)',
                        ),
                        height=140,
                        margin=dict(l=60, r=10, t=28, b=10),
                        paper_bgcolor='rgba(0,0,0,0)',
                        plot_bgcolor='rgba(0,0,0,0)',
                    )
                    live_chart_slot.plotly_chart(
                        fig_spark, use_container_width=True
                    )

        results = run_full_simulation(
            legs, dist_matrix, vessel, sim_config, progress_callback,
            port_charge_vol=port_charge_vol,
            congestion_vol=congestion_vol,
            use_stevedoring=not fio_cargo,
        )
        elapsed   = time.time() - start_time
        iters_sec = len(results) / max(elapsed, 0.001)

        update_best_metrics(results)

        live_status.markdown(
            f"<div style='text-align:center;background:#dcfce7;"
            f"color:#166534;font-weight:700;padding:10px;"
            f"border-radius:8px;font-size:1rem'>"
            f"✅ Complete — {len(results):,} iterations in "
            f"{elapsed:.1f}s ({iters_sec:.0f} iter/sec)"
            f"</div>",
            unsafe_allow_html=True
        )

        analysis = analyse_results(results, ports)

        # ── Write diagnostic log ──────────────────────────────────────────
        try:
            import modules.data_processor as _dp
            _log_text = build_simulation_log(
                elapsed=elapsed,
                sim_config=sim_config,
                vessel=vessel,
                algo_display=algo_choice,
                legs_df=legs,
                analysis=analysis,
                filter_stats=_dp._FILTER_STATS,
            )
            _log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "simulation_log.txt")
            write_simulation_log(_log_text, _log_path)
            st.session_state['sim_log']      = _log_text
            st.session_state['sim_log_path'] = _log_path
        except Exception as _log_err:
            st.session_state['sim_log'] = f"Log generation failed: {_log_err}"

        st.session_state['results']     = results
        st.session_state['analysis']    = analysis
        st.session_state['elapsed']     = elapsed
        st.session_state['vessel']      = vessel
        st.session_state['dist_matrix'] = dist_matrix
        st.session_state['legs_df']     = legs
        st.session_state['sim_running'] = False
        st.session_state['sim_done']    = True

    overlay.empty()

    # ── Completion celebration banner ─────────────────────────────────────
    best_r        = max(results, key=lambda r: r['total_profit'])
    elapsed_total = elapsed
    st.markdown(
        f"<div style='background:linear-gradient(135deg,#166534,#15803d);"
        f"border-radius:16px;padding:24px 28px;margin:16px 0;"
        f"text-align:center'>"
        f"<div style='font-size:1.1rem;color:#86efac;font-weight:600;"
        f"margin-bottom:8px'>✅ COMPASS Simulation Complete</div>"
        f"<div style='display:flex;justify-content:center;gap:40px;flex-wrap:wrap'>"
        f"<div><div style='font-size:2rem;font-weight:700;color:white'>"
        f"${best_r['total_profit']:,.0f}</div>"
        f"<div style='font-size:11px;color:#86efac'>Best Programme Profit</div></div>"
        f"<div><div style='font-size:2rem;font-weight:700;color:white'>"
        f"${best_r['avg_tce']:,.0f}/day</div>"
        f"<div style='font-size:11px;color:#86efac'>Best TCE</div></div>"
        f"<div><div style='font-size:2rem;font-weight:700;color:white'>"
        f"{n_iterations:,}</div>"
        f"<div style='font-size:11px;color:#86efac'>Iterations</div></div>"
        f"<div><div style='font-size:2rem;font-weight:700;color:white'>"
        f"{elapsed_total:.0f}s</div>"
        f"<div style='font-size:11px;color:#86efac'>Duration</div></div>"
        f"</div></div>",
        unsafe_allow_html=True
    )

    # Rerun so all tabs render with the newly stored results
    st.rerun()

# ─── TAB 6: VOYAGE ANALYSIS ──────────────────────────────────────────────────
with tabs[4]:
    if 'analysis' not in st.session_state:
        st.info(
            "Run the simulation first — click 🚀 Run Simulation "
            "in the sidebar to generate voyage programmes."
        )
    else:
        import math as _math

        analysis  = st.session_state['analysis']
        vessel    = st.session_state.get('vessel')
        top_progs = analysis['top_programmes']

        intra_va, ports_va, dist_matrix_va, legs_va = load_data(DATA_PATH)
        port_coords_va  = dict(zip(
            ports_va['Port'], zip(ports_va['Lat'], ports_va['Lon'])
        ))
        port_country_va = dict(zip(ports_va['Port'], ports_va['Country']))

        from data.port_charges import PORT_CHARGES, PORT_CHARGES_DEFAULT
        def _get_meta(pname):
            pc = PORT_CHARGES.get(pname, PORT_CHARGES_DEFAULT)
            return {
                'nav':     pc.get('nav', 10000),
                'cong':    pc.get('cong_mean', 1.0),
                'country': port_country_va.get(pname, '—'),
            }

        def _calc_nm(pa, pb):
            """Haversine NM with maritime routing correction factor."""
            if pa not in port_coords_va or pb not in port_coords_va:
                return 0
            la1, lo1 = port_coords_va[pa]
            la2, lo2 = port_coords_va[pb]
            R = 3440.065
            dlat = _math.radians(la2 - la1)
            dlon = _math.radians(lo2 - lo1)
            a = (_math.sin(dlat/2)**2
                 + _math.cos(_math.radians(la1)) * _math.cos(_math.radians(la2))
                 * _math.sin(dlon/2)**2)
            straight = 2 * R * _math.asin(_math.sqrt(a))
            c1 = port_country_va.get(pa, '')
            c2 = port_country_va.get(pb, '')
            f = (1.45 if c1 == 'Indonesia' and c2 == 'Indonesia'
                 else 1.40 if 'Bangladesh' in [c1, c2]
                 else 1.35 if 'Philippines' in [c1, c2]
                 else 1.25)
            return round(straight * f)

        def _geodesic(lat1, lon1, lat2, lon2, n=80):
            """Build geodesic arc between two coordinates."""
            if lat1 == lat2 and lon1 == lon2:
                return [lat1], [lon1]
            la1 = _math.radians(lat1); lo1 = _math.radians(lon1)
            la2 = _math.radians(lat2); lo2 = _math.radians(lon2)
            d = 2 * _math.asin(_math.sqrt(
                _math.sin((la2-la1)/2)**2
                + _math.cos(la1) * _math.cos(la2)
                * _math.sin((lo2-lo1)/2)**2
            ))
            if d == 0:
                return [lat1, lat2], [lon1, lon2]
            lats, lons = [], []
            for i in range(n + 1):
                f = i / n
                A = _math.sin((1-f)*d) / _math.sin(d)
                B = _math.sin(f*d)     / _math.sin(d)
                x = (A*_math.cos(la1)*_math.cos(lo1)
                     + B*_math.cos(la2)*_math.cos(lo2))
                y = (A*_math.cos(la1)*_math.sin(lo1)
                     + B*_math.cos(la2)*_math.sin(lo2))
                z = A*_math.sin(la1) + B*_math.sin(la2)
                lats.append(_math.degrees(_math.atan2(z, _math.sqrt(x*x + y*y))))
                lons.append(_math.degrees(_math.atan2(y, x)))
            return lats, lons

        def _get_route_lats_lons(port_a, port_b, p_coords):
            """
            Return (lats, lons) for the sea route between two ports.
            Uses real searoute waypoints when available; falls back to
            geodesic arc so existing rendering is never broken.
            """
            try:
                from data.sea_distances_loader import get_sea_route_coords
                waypoints = get_sea_route_coords(port_a, port_b)
                if waypoints and len(waypoints) > 2:
                    # waypoints are [lon, lat] — unzip to separate lists
                    lons = [w[0] for w in waypoints]
                    lats = [w[1] for w in waypoints]
                    return lats, lons
            except Exception:
                pass
            # Fallback: geodesic arc
            if port_a in p_coords and port_b in p_coords:
                la1, lo1 = p_coords[port_a]
                la2, lo2 = p_coords[port_b]
                return _geodesic(la1, lo1, la2, lo2)
            return [], []

        # ── Programme selector header ─────────────────────────────────────
        hcol1, hcol2, hcol3 = st.columns([3, 1, 1])
        with hcol1:
            prog_opts = [
                f"#{p['rank']}  —  ${p['total_profit']:,.0f}  —  "
                f"{p['n_voyages']} voyages  —  TCE ${p['avg_tce']:,.0f}/day"
                for p in top_progs
            ]
            sel_prog_idx = st.selectbox(
                "Programme",
                range(len(top_progs)),
                format_func=lambda i: prog_opts[i],
                key='va_prog_sel',
                label_visibility='collapsed',
            )
        prog_va   = top_progs[sel_prog_idx]
        legs_list = prog_va['legs']

        with hcol2:
            st.metric("Annual Profit", f"${prog_va['total_profit']:,.0f}")
        with hcol3:
            try:
                excel_bytes = export_programme_to_excel(
                    prog_va, vessel, prog_va['rank']
                )
                st.download_button(
                    label="📥 Export Excel",
                    data=excel_bytes,
                    file_name=f"voyage_analysis_{prog_va['rank']}.xlsx",
                    mime=(
                        "application/vnd.openxmlformats-officedocument"
                        ".spreadsheetml.sheet"
                    ),
                    use_container_width=True,
                )
            except Exception:
                pass

        st.markdown("---")

        # ── Selected voyage tracker ───────────────────────────────────────
        va_key = f"va_sel_{sel_prog_idx}"
        if va_key not in st.session_state:
            st.session_state[va_key] = 0
        sel_idx = min(st.session_state[va_key], len(legs_list) - 1)

        # ════════════════════════════════════════════════════════════════
        # ZONE 1 — Left: voyage list + cum chart | Right: config + P&L
        # ════════════════════════════════════════════════════════════════
        z1_left, z1_right = st.columns([2, 3], gap="large")

        # ── LEFT: Compact voyage list ─────────────────────────────────
        with z1_left:
            st.markdown(
                "<div style='font-size:12px;color:#64748b;"
                "margin-bottom:6px'>Click any voyage to explore</div>",
                unsafe_allow_html=True
            )

            for i, leg in enumerate(legs_list):
                pl   = leg.get('profit_loss', leg.get('profit', 0))
                is_s = (i == sel_idx)
                tg_bg = "#dcfce7" if pl >= 0 else "#fee2e2"
                tg_tx = "#166534" if pl >= 0 else "#991b1b"
                sign  = "+" if pl >= 0 else ""

                bc1, bc2 = st.columns([3, 1])
                with bc1:
                    lbl = (
                        f"{'▼ ' if is_s else ''}"
                        f"**{i+1}.** "
                        f"{leg.get('origin_port','?')} → "
                        f"{leg.get('dest_port','?')}"
                    )
                    if st.button(
                        lbl,
                        key=f"va_btn_{sel_prog_idx}_{i}",
                        use_container_width=True,
                        type="secondary",
                    ):
                        st.session_state[va_key] = i
                        st.rerun()
                with bc2:
                    st.markdown(
                        f"<div style='text-align:right;padding-top:4px'>"
                        f"<span style='font-size:11px;background:{tg_bg};"
                        f"color:{tg_tx};padding:2px 7px;border-radius:12px;"
                        f"font-weight:500'>{sign}${pl/1000:.0f}k</span>"
                        f"<div style='font-size:10px;color:#94a3b8;"
                        f"text-align:right;margin-top:1px'>"
                        f"{leg.get('total_days',0):.1f}d</div></div>",
                        unsafe_allow_html=True
                    )

            # Cumulative profit bar chart
            st.markdown(
                "<div style='font-size:11px;color:#94a3b8;"
                "margin-top:10px;margin-bottom:4px'>"
                "Cumulative profit build-up</div>",
                unsafe_allow_html=True
            )
            cum_vals  = [l.get('cum_profit', 0) for l in legs_list]
            pl_vals   = [l.get('profit_loss', l.get('profit', 0))
                         for l in legs_list]
            bar_colors_va = [
                '#22c55e' if v >= 0 else '#ef4444' for v in pl_vals
            ]
            bar_colors_va[sel_idx] = '#f59e0b'

            fig_cum_va = go.Figure()
            fig_cum_va.add_trace(go.Bar(
                x=list(range(1, len(legs_list) + 1)),
                y=cum_vals,
                marker_color=bar_colors_va,
                showlegend=False,
                hovertemplate='Voyage %{x}<br>Cum: $%{y:,.0f}<extra></extra>',
            ))
            fig_cum_va.add_hline(y=0, line_color='#1a3a5c', line_width=1)
            fig_cum_va.add_vline(
                x=sel_idx + 1, line_color='#f59e0b',
                line_width=2, line_dash='dot',
            )
            fig_cum_va.update_layout(
                height=160, margin=dict(l=0, r=0, t=0, b=0),
                plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                xaxis=dict(title='Voyage', tickfont=dict(size=9),
                           gridcolor='rgba(0,0,0,0.05)'),
                yaxis=dict(tickformat='$,.0f', tickfont=dict(size=9),
                           gridcolor='rgba(0,0,0,0.05)'),
            )
            st.plotly_chart(fig_cum_va, use_container_width=True)

        # ── RIGHT: Config cards + P&L ─────────────────────────────────
        with z1_right:
            sel_leg = legs_list[sel_idx]
            pl_val  = sel_leg.get('profit_loss', sel_leg.get('profit', 0))
            pl_col_h = "#166534" if pl_val >= 0 else "#991b1b"
            pl_bg_h  = "#dcfce7" if pl_val >= 0 else "#fee2e2"

            st.markdown(
                f"<div style='background:#f8fafc;border:0.5px solid #e2e8f0;"
                f"border-radius:10px;padding:10px 14px;margin-bottom:10px;"
                f"display:flex;align-items:center;gap:12px;flex-wrap:wrap'>"
                f"<span style='font-size:14px;font-weight:600;color:#1a3a5c'>"
                f"Voyage {sel_idx+1} of {len(legs_list)}</span>"
                f"<span style='font-size:13px;color:#475569'>"
                f"{sel_leg.get('origin_port','?')} → "
                f"{sel_leg.get('dest_port','?')}</span>"
                f"<span style='background:#e6f1fb;color:#0c447c;"
                f"font-size:11px;padding:2px 8px;border-radius:10px'>"
                f"{sel_leg.get('commodity','')}</span>"
                f"<span style='margin-left:auto;background:{pl_bg_h};"
                f"color:{pl_col_h};font-size:13px;font-weight:600;"
                f"padding:3px 10px;border-radius:10px'>"
                f"{'+'if pl_val>=0 else ''}${pl_val:,.0f}</span>"
                f"</div>",
                unsafe_allow_html=True
            )

            # ── Cargo intelligence badges ──────────────────────────────
            _ci_badges = []
            _hold_switch  = sel_leg.get('hold_switch', '')
            _cleaning_cost = sel_leg.get('cleaning_cost', 0)
            _cleaning_days = sel_leg.get('cleaning_days', 0.0)
            _seasonal_f   = sel_leg.get('seasonal_factor', 1.0)
            _sim_month    = sel_leg.get('sim_month', 1)
            _month_name   = ["Jan","Feb","Mar","Apr","May","Jun",
                             "Jul","Aug","Sep","Oct","Nov","Dec"][max(0, _sim_month - 1)]

            if _hold_switch and _cleaning_cost > 0:
                try:
                    from data.cargo_intelligence import get_cleaning_cost as _gcc
                    _prev_c = _hold_switch.split(' -> ')[0] if ' -> ' in _hold_switch else ''
                    _next_c = sel_leg.get('commodity', '')
                    _grade  = _gcc(_prev_c, _next_c).get('grade', 'G')
                except Exception:
                    _grade = 'G'
                _gc = {"G":"#dcfce7","W":"#fef3c7","S":"#fee2e2","X":"#fee2e2"}.get(_grade,"#e6f1fb")
                _tc = {"G":"#166534","W":"#92400e","S":"#991b1b","X":"#991b1b"}.get(_grade,"#0c447c")
                _ci_badges.append(
                    f"<span style='background:{_gc};color:{_tc};"
                    f"font-size:10px;padding:2px 8px;border-radius:8px;white-space:nowrap'>"
                    f"Hold clean: {_hold_switch} | Grade {_grade} | "
                    f"{_cleaning_days:.1f}d | ${_cleaning_cost:,.0f}</span>"
                )

            if abs(_seasonal_f - 1.0) >= 0.01:
                _sf_bg  = "#dcfce7" if _seasonal_f >= 1.0 else "#fee2e2"
                _sf_tc  = "#166534" if _seasonal_f >= 1.0 else "#991b1b"
                _sf_sym = "+" if _seasonal_f >= 1.0 else ""
                _ci_badges.append(
                    f"<span style='background:{_sf_bg};color:{_sf_tc};"
                    f"font-size:10px;padding:2px 8px;border-radius:8px;white-space:nowrap'>"
                    f"Seasonal {_month_name}: ×{_seasonal_f:.2f} "
                    f"({_sf_sym}{(_seasonal_f-1)*100:.0f}%)</span>"
                )

            if _ci_badges:
                st.markdown(
                    "<div style='display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px'>"
                    + "".join(_ci_badges) + "</div>",
                    unsafe_allow_html=True
                )

            cc1, cc2, cc3 = st.columns(3)

            # ── Card 1: Ports ──────────────────────────────────────────
            with cc1:
                st.markdown(
                    "<div style='font-size:10px;font-weight:600;color:#64748b;"
                    "text-transform:uppercase;letter-spacing:.06em;"
                    "margin-bottom:6px'>Ports</div>",
                    unsafe_allow_html=True
                )
                all_load  = sorted(legs_va['origin_port'].unique().tolist())
                all_disch = sorted(legs_va['dest_port'].unique().tolist())
                all_comm  = sorted(legs_va['commodity'].unique().tolist())

                cur_load  = sel_leg.get('origin_port',  all_load[0])
                cur_disch = sel_leg.get('dest_port',    all_disch[0])
                cur_comm  = sel_leg.get('commodity',    all_comm[0])

                new_load = st.selectbox(
                    "Load port", all_load,
                    index=(all_load.index(cur_load)
                           if cur_load in all_load else 0),
                    key=f'va_load_{sel_prog_idx}_{sel_idx}',
                )
                new_disch = st.selectbox(
                    "Discharge port", all_disch,
                    index=(all_disch.index(cur_disch)
                           if cur_disch in all_disch else 0),
                    key=f'va_disch_{sel_prog_idx}_{sel_idx}',
                )
                new_comm = st.selectbox(
                    "Commodity", all_comm,
                    index=(all_comm.index(cur_comm)
                           if cur_comm in all_comm else 0),
                    key=f'va_comm_{sel_prog_idx}_{sel_idx}',
                )
                _sim_load_c  = sel_leg.get('origin_port', '')
                _sim_disch_c = sel_leg.get('dest_port', '')
                _ports_changed_c = (new_load != _sim_load_c
                                    or new_disch != _sim_disch_c)
                if _ports_changed_c:
                    load_meta  = _get_meta(new_load)
                    disch_meta = _get_meta(new_disch)
                    _lnav  = load_meta['nav']
                    _dnav  = disch_meta['nav']
                    _lcong = load_meta['cong']
                    _dcong = disch_meta['cong']
                else:
                    _lnav  = int(sel_leg.get('load_port_nav',  10000))
                    _dnav  = int(sel_leg.get('disch_port_nav', 10000))
                    _lcong = float(sel_leg.get('load_cong_days',  1.0))
                    _dcong = float(sel_leg.get('disch_cong_days', 1.0))
                st.markdown(
                    f"<div style='font-size:10px;color:#64748b;margin-top:4px'>"
                    f"Load nav: <b>${_lnav:,}</b> · "
                    f"Cong: <b>{_lcong:.1f}d</b><br>"
                    f"Disch nav: <b>${_dnav:,}</b> · "
                    f"Cong: <b>{_dcong:.1f}d</b>"
                    f"<span style='font-size:9px;color:#94a3b8;margin-left:4px'>"
                    f"{'(calc)' if _ports_changed_c else '(sim)'}</span>"
                    f"</div>",
                    unsafe_allow_html=True
                )

            # ── Card 2: Distances & Days ───────────────────────────────
            with cc2:
                st.markdown(
                    "<div style='font-size:10px;font-weight:600;color:#64748b;"
                    "text-transform:uppercase;letter-spacing:.06em;"
                    "margin-bottom:6px'>Distances &amp; days</div>",
                    unsafe_allow_html=True
                )
                # Check if ports changed from simulation values
                _sim_load  = sel_leg.get('origin_port', '')
                _sim_disch = sel_leg.get('dest_port', '')
                _ports_changed = (new_load != _sim_load or new_disch != _sim_disch)

                _prev_port = (
                    legs_list[sel_idx-1].get('dest_port', 'prev')
                    if sel_idx > 0 else 'start'
                )
                _sim_prev = (
                    legs_list[sel_idx-1].get('dest_port', '')
                    if sel_idx > 0 else ''
                )
                _ballast_changed = (new_load != _sim_load or _prev_port != _sim_prev)

                # Use simulation NM if ports unchanged, else calculate from coords
                if _ports_changed:
                    _default_laden = float(_calc_nm(new_load, new_disch))
                    _laden_label   = f"Laden NM (calc: {_default_laden:,.0f})"
                else:
                    _default_laden = float(sel_leg.get(
                        'laden_nm', _calc_nm(new_load, new_disch)
                    ))
                    _laden_label   = f"Laden NM (sim: {_default_laden:,.0f})"

                if _ballast_changed:
                    _default_ballast = float(
                        _calc_nm(_prev_port, new_load) if sel_idx > 0 else 0
                    )
                else:
                    _default_ballast = float(sel_leg.get('ballast_nm', 0))

                prev_lbl = (
                    f"from {_prev_port}" if sel_idx > 0 else "first voyage"
                )
                # Default speeds from vessel config
                _spd_l_default = vessel.speed_laden_knots   if vessel else 11.0
                _spd_b_default = vessel.speed_ballast_knots if vessel else 11.5

                # Speed inputs — editable per voyage (sequential, no nested columns)
                spd_l = st.number_input(
                    "Laden speed (kn)",
                    value=float(_spd_l_default),
                    min_value=6.0, max_value=18.0, step=0.5,
                    key=f'va_spdl_{sel_prog_idx}_{sel_idx}',
                    help="Vessel speed when loaded"
                )
                spd_b = st.number_input(
                    "Ballast speed (kn)",
                    value=float(_spd_b_default),
                    min_value=6.0, max_value=18.0, step=0.5,
                    key=f'va_spdb_{sel_prog_idx}_{sel_idx}',
                    help="Vessel speed when empty"
                )

                laden_nm = st.number_input(
                    _laden_label,
                    value=_default_laden,
                    min_value=0.0, step=10.0,
                    key=f'va_lnm_{sel_prog_idx}_{sel_idx}_{new_load}_{new_disch}',
                    help=(
                        "Loaded from simulation data (D1 matrix). "
                        "Changes automatically when you select a different port."
                        if not _ports_changed else
                        "Calculated from port coordinates. Override if needed."
                    )
                )
                laden_days = laden_nm / (spd_l * 24) if spd_l > 0 else 0
                st.caption(f"@ {spd_l} kn → **{laden_days:.2f} days**")

                ballast_nm = st.number_input(
                    f"Ballast NM ({prev_lbl})",
                    value=_default_ballast,
                    min_value=0.0, step=10.0,
                    key=f'va_bnm_{sel_prog_idx}_{sel_idx}_{_prev_port}_{new_load}',
                )
                ballast_days = (
                    ballast_nm / (spd_b * 24)
                    if ballast_nm > 0 and spd_b > 0 else 0
                )
                st.caption(f"@ {spd_b} kn → **{ballast_days:.2f} days**")

                st.markdown(
                    f"<div style='background:#f0f9ff;border:0.5px solid "
                    f"#bae6fd;border-radius:6px;padding:6px 8px;"
                    f"margin-top:4px;font-size:11px;color:#0369a1'>"
                    f"Total sailing: "
                    f"<b>{laden_days+ballast_days:.2f} days</b></div>",
                    unsafe_allow_html=True
                )

            # ── Card 3: Cargo & Freight ────────────────────────────────
            with cc3:
                st.markdown(
                    "<div style='font-size:10px;font-weight:600;color:#64748b;"
                    "text-transform:uppercase;letter-spacing:.06em;"
                    "margin-bottom:6px'>Cargo &amp; freight</div>",
                    unsafe_allow_html=True
                )
                dwcc_v = vessel.dwcc if vessel else 15000
                new_cargo = st.number_input(
                    "Cargo (MT)",
                    value=float(sel_leg.get('cargo_mt', dwcc_v)),
                    min_value=1000.0, max_value=float(dwcc_v),
                    step=500.0,
                    key=f'va_cargo_{sel_prog_idx}_{sel_idx}_{new_load}_{new_disch}',
                )
                new_rate = st.number_input(
                    "Freight rate ($/MT)",
                    value=float(round(sel_leg.get('freight_rate', 15.0), 2)),
                    min_value=1.0, max_value=200.0, step=0.5,
                    key=f'va_rate_{sel_prog_idx}_{sel_idx}_{new_comm}',
                )
                gross_c = new_cargo * new_rate
                ni_c    = gross_c * (1 - (vessel.brokerage_pct if vessel else 0.0375))
                st.markdown(
                    f"<div style='background:#f8fafc;border:0.5px solid "
                    f"#e2e8f0;border-radius:6px;padding:6px 8px;margin-top:4px'>"
                    f"<div style='font-size:10px;color:#64748b'>Gross freight</div>"
                    f"<div style='font-size:16px;font-weight:600;color:#1a3a5c'>"
                    f"${gross_c:,.0f}</div>"
                    f"<div style='font-size:10px;color:#64748b;margin-top:2px'>"
                    f"Net income: ${ni_c:,.0f}</div></div>",
                    unsafe_allow_html=True
                )
                st.markdown("<br>", unsafe_allow_html=True)
                recalc_va = st.button(
                    "Recalculate",
                    key=f'va_recalc_{sel_prog_idx}_{sel_idx}',
                    use_container_width=True,
                    type="primary",
                )
                st.button(
                    "Cascade ↗",
                    key=f'va_casc_{sel_prog_idx}_{sel_idx}',
                    use_container_width=True,
                )

            # ── Live P&L computation ──────────────────────────────────
            computed_va = None
            if vessel:
                try:
                    from modules.simulation_engine import cost_voyage_exact
                    from modules.data_processor import (
                        CARGO_RATE, COMMODITY_CATEGORIES
                    )
                    cat_va   = COMMODITY_CATEGORIES.get(new_comm, 'Dry Bulk')
                    rates_va = CARGO_RATE.get(
                        cat_va, {'load': 5000, 'disch': 4000}
                    )

                    # Port charges: simulation values when ports unchanged
                    if _ports_changed:
                        lm_va = _get_meta(new_load)
                        dm_va = _get_meta(new_disch)
                        _load_nav   = lm_va['nav']
                        _disch_nav  = dm_va['nav']
                        _load_cong  = lm_va['cong']
                        _disch_cong = dm_va['cong']
                    else:
                        _load_nav   = float(sel_leg.get('load_port_nav',  10000))
                        _disch_nav  = float(sel_leg.get('disch_port_nav', 10000))
                        _load_cong  = float(sel_leg.get('load_cong_days',  1.0))
                        _disch_cong = float(sel_leg.get('disch_cong_days', 1.0))

                    vessel_override = VesselConfig(
                        dwt=vessel.dwt,
                        dwcc=vessel.dwcc,
                        speed_laden_knots=spd_l,
                        speed_ballast_knots=spd_b,
                        charter_hire_day=vessel.charter_hire_day,
                        lsfo_price_mt=vessel.lsfo_price_mt,
                        mgo_price_mt=vessel.mgo_price_mt,
                        insurance_annual=vessel.insurance_annual,
                        brokerage_pct=vessel.brokerage_pct,
                        operating_days_year=vessel.operating_days_year,
                    )
                    computed_va = cost_voyage_exact(
                        cargo_mt=new_cargo,
                        freight_rate=new_rate,
                        laden_nm=laden_nm,
                        ballast_nm=ballast_nm,
                        load_rate_mt_day=rates_va['load'],
                        disch_rate_mt_day=rates_va['disch'],
                        load_port_nav=_load_nav,
                        load_port_steve=0,
                        disch_port_nav=_disch_nav,
                        disch_port_steve=0,
                        vessel=vessel_override,
                        load_cong_days=_load_cong,
                        disch_cong_days=_disch_cong,
                    )
                except Exception:
                    computed_va = None

            if recalc_va and computed_va:
                st.success(
                    f"Recalculated — "
                    f"P&L: {'+'if computed_va['profit_loss']>=0 else ''}"
                    f"${computed_va['profit_loss']:,.0f}  |  "
                    f"TCE: ${computed_va['profit_per_day']:,.0f}/day"
                )

            st.markdown("---")

            # ── P&L table + Waterfall chart ───────────────────────────
            pl_col_l, wf_col_r = st.columns(2)

            def _v_va(k, fb=0):
                if computed_va and k in computed_va:
                    return computed_va[k]
                return sel_leg.get(k, fb)

            g_va   = _v_va('gross_freight', sel_leg.get('revenue', 0))
            br_va  = _v_va('brokerage')
            ni_va  = _v_va('net_income')
            ch_va  = _v_va('charter_hire', sel_leg.get('charter_hire_cost', 0))
            lc_va  = _v_va('lsfo_cost')
            mc_va  = _v_va('mgo_cost')
            tb_va  = lc_va + mc_va
            pc_va  = _v_va('port_costs',
                            sel_leg.get('load_port_nav', 0)
                            + sel_leg.get('disch_port_nav', 0))
            ins_va = _v_va('insurance')
            oth_va = _v_va('other_costs', 1000)
            exp_va = _v_va('total_expenses', sel_leg.get('total_cost', 0))
            pl_va  = _v_va('profit_loss',   sel_leg.get('profit', 0))
            ppd_va = _v_va('profit_per_day')
            td_va  = _v_va('total_days',    sel_leg.get('total_days', 0))
            vs_avg_va = ppd_va - prog_va['avg_tce']

            with pl_col_l:
                st.markdown(
                    "<div style='font-size:10px;font-weight:600;color:#64748b;"
                    "text-transform:uppercase;letter-spacing:.06em;"
                    "margin-bottom:8px'>P&amp;L breakdown — two phases</div>",
                    unsafe_allow_html=True
                )

                # ── Pull phase data (prefer computed_va, fall back to sel_leg) ──
                _src = computed_va if computed_va else sel_leg
                _bp = _src.get('ballast_phase', sel_leg.get('ballast_phase', {}))
                _lp = _src.get('laden_phase',   sel_leg.get('laden_phase', {}))

                b_nm_va   = _bp.get('nm',   _v_va('ballast_nm', sel_leg.get('ballast_distance_nm', 0)))
                b_days_va = _bp.get('days', _v_va('ballast_days', 0))
                b_hire_va = _bp.get('charter_cost', 0)
                b_bunk_va = _bp.get('bunker_cost',  0)
                b_cost_va = _bp.get('total_cost',   b_hire_va + b_bunk_va)

                l_nm_va   = _lp.get('nm',   _v_va('laden_nm', sel_leg.get('distance_nm', 0)))
                l_days_va = _lp.get('days', _v_va('laden_days', 0))

                # Phase 1 rows
                ph1_rows = [
                    ("Charter hire",  -b_hire_va, False),
                    ("Bunker (LSFO)", -b_bunk_va, False),
                    ("Revenue",        0,          False),
                    ("Phase 1 total", -b_cost_va, True),
                ]
                ph1_html = ""
                for _lbl, _val, _sub in ph1_rows:
                    _vc  = "#991b1b" if _val < 0 else "#64748b" if _val == 0 else "#166534"
                    _fw  = "600" if _sub else "400"
                    _bdr = "border-top:0.5px solid #e2e8f0;padding-top:4px;" if _sub else ""
                    _txt = "$0" if _val == 0 else f"{'+'if _val>0 else ''}${abs(_val):,.0f}"
                    ph1_html += (
                        f"<tr style='{_bdr}'>"
                        f"<td style='padding:2px 0;font-size:11px;color:#475569;font-weight:{_fw}'>{_lbl}</td>"
                        f"<td style='text-align:right;font-size:11px;color:{_vc};font-weight:{_fw}'>{_txt}</td>"
                        f"</tr>"
                    )

                # Phase 2 rows (use existing _v_va values)
                ph2_items = [
                    ("Gross freight",      g_va,              False, False),
                    ("Brokerage (3.75%)", -br_va,             True,  False),
                    ("Net income",         ni_va,             False, True),
                    ("Charter hire",      -ch_va,             True,  False),
                    ("LSFO bunker",       -lc_va,             True,  False),
                    ("MGO bunker",        -mc_va,             True,  False),
                    ("Total bunker",      -tb_va,             True,  True),
                    ("Port charges",      -pc_va,             True,  False),
                    ("Insurance + other", -(ins_va + oth_va), True,  False),
                    ("Total expenses",    -exp_va,            True,  True),
                ]
                ph2_html = ""
                for _lbl2, _val2, _cost2, _sub2 in ph2_items:
                    _vc2  = "#166534" if _val2 > 0 and not _cost2 else "#991b1b" if _val2 < 0 else "#1a3a5c"
                    _fw2  = "600" if _sub2 else "400"
                    _bdr2 = "border-top:0.5px solid #e2e8f0;padding-top:4px;" if _sub2 else ""
                    ph2_html += (
                        f"<tr style='{_bdr2}'>"
                        f"<td style='padding:2px 0;font-size:11px;color:#475569;font-weight:{_fw2}'>{_lbl2}</td>"
                        f"<td style='text-align:right;font-size:11px;color:{_vc2};font-weight:{_fw2}'>"
                        f"{'+'if _val2>0 else ''}${abs(_val2):,.0f}</td></tr>"
                    )

                pl_c_va  = "#166534" if pl_va >= 0 else "#991b1b"
                vs_c_va  = "#166534" if vs_avg_va >= 0 else "#991b1b"
                vs_s_va  = "+" if vs_avg_va >= 0 else ""
                _br_pct  = b_days_va / max(td_va, 1) * 100

                st.markdown(
                    # Phase 1 header
                    f"<div style='background:#FEF3C7;border-left:3px solid #F59E0B;"
                    f"border-radius:0 6px 6px 0;padding:5px 8px;margin-bottom:4px'>"
                    f"<span style='font-size:11px;font-weight:600;color:#92400E'>"
                    f"Phase 1 — Ballast (empty)</span>"
                    f"<span style='float:right;font-size:10px;color:#92400E'>"
                    f"{b_nm_va:,.0f} NM · {b_days_va:.1f} d</span></div>"
                    f"<table style='width:100%;border-collapse:collapse'>"
                    f"{ph1_html}</table>"
                    # Phase 2 header
                    f"<div style='background:#DCFCE7;border-left:3px solid #22C55E;"
                    f"border-radius:0 6px 6px 0;padding:5px 8px;margin:8px 0 4px 0'>"
                    f"<span style='font-size:11px;font-weight:600;color:#166534'>"
                    f"Phase 2 — Laden (loaded)</span>"
                    f"<span style='float:right;font-size:10px;color:#166534'>"
                    f"{l_nm_va:,.0f} NM · {l_days_va:.1f} d</span></div>"
                    f"<table style='width:100%;border-collapse:collapse'>"
                    f"{ph2_html}"
                    # Net total footer
                    f"<tr style='border-top:2px solid #1a3a5c'>"
                    f"<td style='padding:4px 0;font-size:13px;font-weight:700;color:#1a3a5c'>Net voyage profit</td>"
                    f"<td style='text-align:right;font-size:15px;font-weight:700;color:{pl_c_va}'>"
                    f"{'+'if pl_va>=0 else ''}${pl_va:,.0f}</td></tr>"
                    f"<tr><td style='font-size:10px;color:#94a3b8;padding:2px 0'>TCE this voyage</td>"
                    f"<td style='text-align:right;font-size:10px;color:#475569'>${ppd_va:,.0f}/day</td></tr>"
                    f"<tr><td style='font-size:10px;color:#94a3b8'>vs programme avg</td>"
                    f"<td style='text-align:right;font-size:10px;color:{vs_c_va}'>{vs_s_va}${vs_avg_va:,.0f}/day</td></tr>"
                    f"<tr><td style='font-size:10px;color:#94a3b8'>Ballast ratio</td>"
                    f"<td style='text-align:right;font-size:10px;color:#92400E'>{_br_pct:.0f}% empty</td></tr>"
                    f"<tr><td style='font-size:10px;color:#94a3b8'>Total voyage days</td>"
                    f"<td style='text-align:right;font-size:10px;color:#475569'>{td_va:.1f} days</td></tr>"
                    f"</table>",
                    unsafe_allow_html=True
                )

            with wf_col_r:
                st.markdown(
                    "<div style='font-size:10px;font-weight:600;color:#64748b;"
                    "text-transform:uppercase;letter-spacing:.06em;"
                    "margin-bottom:8px'>Waterfall chart</div>",
                    unsafe_allow_html=True
                )
                wf_labels_va = [
                    'Gross', 'Brokerage', 'Net inc',
                    'Hire', 'Bunker', 'Port', 'Ins+oth', 'Profit'
                ]
                wf_values_va = [
                    g_va, -br_va, ni_va,
                    -ch_va, -tb_va, -pc_va,
                    -(ins_va+oth_va), pl_va
                ]
                wf_colors_va = [
                    '#378ADD', '#ef4444', '#378ADD',
                    '#ef4444', '#ef4444', '#ef4444', '#ef4444',
                    '#22c55e' if pl_va >= 0 else '#ef4444'
                ]
                fig_wf_va = go.Figure(go.Bar(
                    x=wf_labels_va,
                    y=[abs(v) for v in wf_values_va],
                    marker_color=wf_colors_va,
                    text=[f"${abs(v)/1000:.0f}k" for v in wf_values_va],
                    textposition='outside',
                    textfont=dict(size=9),
                    showlegend=False,
                    hovertemplate='%{x}<br>$%{y:,.0f}<extra></extra>',
                ))
                fig_wf_va.update_layout(
                    height=260, margin=dict(l=0, r=0, t=16, b=0),
                    plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                    xaxis=dict(tickfont=dict(size=9)),
                    yaxis=dict(visible=False),
                )
                st.plotly_chart(fig_wf_va, use_container_width=True)

                st.markdown(
                    f"<div style='display:flex;gap:6px;flex-wrap:wrap;"
                    f"margin-top:4px'>"
                    f"<span style='font-size:10px;background:#e6f1fb;"
                    f"color:#0c447c;padding:2px 8px;border-radius:10px'>"
                    f"Load nav: ${_lnav:,}</span>"
                    f"<span style='font-size:10px;background:#e6f1fb;"
                    f"color:#0c447c;padding:2px 8px;border-radius:10px'>"
                    f"Disch nav: ${_dnav:,}</span>"
                    f"<span style='font-size:10px;background:#fef3c7;"
                    f"color:#92400e;padding:2px 8px;border-radius:10px'>"
                    f"Cong: "
                    f"{_lcong+_dcong:.1f}d</span>"
                    f"</div>",
                    unsafe_allow_html=True
                )

        # ════════════════════════════════════════════════════════════════
        # ZONE 2 — Full-width sea route map
        # ════════════════════════════════════════════════════════════════
        st.markdown("---")
        st.markdown(
            f"<div style='font-size:12px;font-weight:600;color:#1a3a5c;"
            f"margin-bottom:6px'>"
            f"Sea route — {new_load} → {new_disch}"
            f"<span style='font-size:11px;font-weight:400;color:#64748b;"
            f"margin-left:8px'>"
            f"Laden: {laden_nm:,.0f} NM · {laden_days:.1f} days  |  "
            f"Ballast: {ballast_nm:,.0f} NM · {ballast_days:.1f} days"
            f"</span></div>",
            unsafe_allow_html=True
        )

        map_traces_va = []

        # Ballast leg — grey dashed line from prev port to load
        if sel_idx > 0 and ballast_nm > 0:
            prev_dest_va = legs_list[sel_idx-1].get('dest_port', '')
            if (prev_dest_va in port_coords_va
                    and new_load in port_coords_va):
                b_lats, b_lons = _get_route_lats_lons(
                    prev_dest_va, new_load, port_coords_va
                )
                if not b_lats:
                    b_lats, b_lons = [port_coords_va[prev_dest_va][0], port_coords_va[new_load][0]], \
                                     [port_coords_va[prev_dest_va][1], port_coords_va[new_load][1]]
                map_traces_va.append(go.Scattermap(
                    lat=b_lats, lon=b_lons, mode='lines',
                    line=dict(width=2, color='#94a3b8'),
                    opacity=0.6, hoverinfo='skip', showlegend=False,
                ))
                bm = len(b_lats) // 2
                map_traces_va.append(go.Scattermap(
                    lat=[b_lats[bm]], lon=[b_lons[bm]],
                    mode='markers+text',
                    marker=dict(size=1, color='rgba(0,0,0,0)'),
                    text=[f"Ballast {ballast_nm:,.0f} NM"],
                    textfont=dict(size=10, color='#64748b'),
                    textposition='top center',
                    hoverinfo='skip', showlegend=False,
                ))

        # Laden leg — main route arc
        if new_load in port_coords_va and new_disch in port_coords_va:
            l_lats, l_lons = _get_route_lats_lons(
                new_load, new_disch, port_coords_va
            )
            route_col_va   = '#f59e0b' if pl_va >= 0 else '#ef4444'

            map_traces_va.append(go.Scattermap(
                lat=l_lats, lon=l_lons, mode='lines',
                line=dict(width=5, color=route_col_va),
                hovertext=(
                    f"<b>Voyage {sel_idx+1} — {new_comm}</b><br>"
                    f"{new_load} → {new_disch}<br>"
                    f"Distance: {laden_nm:,.0f} NM<br>"
                    f"Sailing: {laden_days:.1f} days<br>"
                    f"Cargo: {new_cargo:,.0f} MT @ ${new_rate}/MT<br>"
                    f"P&L: {'+'if pl_va>=0 else ''}${pl_va:,.0f}"
                ),
                hoverinfo='text', showlegend=False,
            ))

            # Distance label at arc midpoint
            lm_va_idx = len(l_lats) // 2
            map_traces_va.append(go.Scattermap(
                lat=[l_lats[lm_va_idx]], lon=[l_lons[lm_va_idx]],
                mode='markers+text',
                marker=dict(size=1, color='rgba(0,0,0,0)'),
                text=[f"{laden_nm:,.0f} NM · {laden_days:.1f} days"],
                textfont=dict(size=11, color='#92400e'),
                textposition='top center',
                hoverinfo='skip', showlegend=False,
            ))

            # Vessel marker at destination
            map_traces_va.append(go.Scattermap(
                lat=[l_lats[-1]], lon=[l_lons[-1]],
                mode='markers',
                marker=dict(size=18, color='#f59e0b'),
                hovertext='Vessel position',
                hoverinfo='text', showlegend=False,
            ))

        # Programme route ports as grey background dots
        route_ports_va = set()
        for lg in legs_list:
            route_ports_va.add(lg.get('origin_port', ''))
            route_ports_va.add(lg.get('dest_port', ''))
        route_ports_va.discard('')
        valid_rp_va = [p for p in route_ports_va if p in port_coords_va]
        if valid_rp_va:
            map_traces_va.append(go.Scattermap(
                lat=[port_coords_va[p][0] for p in valid_rp_va],
                lon=[port_coords_va[p][1] for p in valid_rp_va],
                mode='markers',
                marker=dict(size=5, color='#94a3b8', opacity=0.4),
                hoverinfo='skip', showlegend=False,
            ))

        # Load and discharge port markers
        for pname_va, pcolor_va, psize_va in [
            (new_load,  '#1d4ed8', 16),
            (new_disch, '#dc2626', 16),
        ]:
            if pname_va in port_coords_va:
                meta_va          = _get_meta(pname_va)
                plat_va, plon_va = port_coords_va[pname_va]
                map_traces_va.append(go.Scattermap(
                    lat=[plat_va], lon=[plon_va],
                    mode='markers+text',
                    marker=dict(size=psize_va, color=pcolor_va),
                    text=[pname_va],
                    textposition='top right',
                    textfont=dict(size=11, color='#1e293b'),
                    hovertemplate=(
                        f"<b>{pname_va}</b><br>"
                        f"Country: {meta_va['country']}<br>"
                        f"Port nav charge: ${meta_va['nav']:,}<br>"
                        f"Avg congestion: {meta_va['cong']:.1f} days"
                        f"<extra></extra>"
                    ),
                    showlegend=False,
                ))

        # Map centre between load and discharge
        if new_load in port_coords_va and new_disch in port_coords_va:
            clat_va = (port_coords_va[new_load][0]
                       + port_coords_va[new_disch][0]) / 2
            clon_va = (port_coords_va[new_load][1]
                       + port_coords_va[new_disch][1]) / 2
        else:
            clat_va, clon_va = 10.0, 105.0

        fig_map_va = go.Figure(data=map_traces_va)
        fig_map_va.update_layout(
            mapbox=dict(
                style='carto-positron', zoom=3.5,
                center=dict(lat=clat_va, lon=clon_va),
            ),
            height=520, margin=dict(l=0, r=0, t=0, b=0),
            paper_bgcolor='rgba(0,0,0,0)', showlegend=False,
            hoverlabel=dict(bgcolor='white', bordercolor='#1e293b',
                            font=dict(size=12)),
        )
        st.plotly_chart(fig_map_va, use_container_width=True)

        # Map legend strip
        ml1, ml2, ml3, ml4, ml5 = st.columns(5)
        ml1.markdown(
            "<div style='display:flex;align-items:center;gap:4px'>"
            "<div style='width:10px;height:10px;border-radius:50%;"
            "background:#1d4ed8'></div>"
            "<span style='font-size:11px;color:#475569'>Load port</span>"
            "</div>", unsafe_allow_html=True
        )
        ml2.markdown(
            "<div style='display:flex;align-items:center;gap:4px'>"
            "<div style='width:10px;height:10px;border-radius:50%;"
            "background:#dc2626'></div>"
            "<span style='font-size:11px;color:#475569'>Discharge port"
            "</span></div>", unsafe_allow_html=True
        )
        ml3.markdown(
            "<div style='display:flex;align-items:center;gap:4px'>"
            "<div style='width:22px;height:3px;background:#f59e0b'></div>"
            "<span style='font-size:11px;color:#475569'>Laden route</span>"
            "</div>", unsafe_allow_html=True
        )
        ml4.markdown(
            "<div style='display:flex;align-items:center;gap:4px'>"
            "<div style='width:22px;height:2px;background:#94a3b8'></div>"
            "<span style='font-size:11px;color:#475569'>Ballast leg</span>"
            "</div>", unsafe_allow_html=True
        )
        ml5.markdown(
            f"<div style='text-align:right'>"
            f"<a href='https://www.marinetraffic.com/en/ais/home/"
            f"centerx:{clon_va:.1f}/centery:{clat_va:.1f}/zoom:6' "
            f"style='font-size:11px;color:#0369a1;text-decoration:none'>"
            f"View on MarineTraffic ↗</a></div>",
            unsafe_allow_html=True
        )

# ─── TAB 7: VOYAGE JOURNEY (animated vessel) ─────────────────────────────────
with tabs[5]:
    if 'analysis' not in st.session_state:
        st.info(
            "Run the simulation first — click 🚀 Run Simulation "
            "in the sidebar to generate voyage programmes."
        )
    else:
        import math as _math

        analysis_vj  = st.session_state['analysis']
        vessel_vj    = st.session_state.get('vessel')
        top_progs_vj = analysis_vj['top_programmes']

        intra_vj, ports_vj, dist_matrix_vj, legs_vj = load_data(DATA_PATH)
        port_coords_vj  = dict(zip(
            ports_vj['Port'], zip(ports_vj['Lat'], ports_vj['Lon'])
        ))
        port_country_vj = dict(zip(ports_vj['Port'], ports_vj['Country']))

        from data.port_charges import PORT_CHARGES, PORT_CHARGES_DEFAULT
        from data.sea_distances_loader import get_sea_route_coords

        def _get_meta_vj(pname):
            pc = PORT_CHARGES.get(pname, PORT_CHARGES_DEFAULT)
            return {
                'nav':     pc.get('nav', 10000),
                'cong':    pc.get('cong_mean', 1.0),
                'country': port_country_vj.get(pname, '—'),
            }

        def _calc_nm_vj(pa, pb):
            if pa not in port_coords_vj or pb not in port_coords_vj:
                return 0
            la1, lo1 = port_coords_vj[pa]
            la2, lo2 = port_coords_vj[pb]
            R = 3440.065
            dlat = _math.radians(la2 - la1)
            dlon = _math.radians(lo2 - lo1)
            a = (_math.sin(dlat/2)**2
                 + _math.cos(_math.radians(la1))
                 * _math.cos(_math.radians(la2))
                 * _math.sin(dlon/2)**2)
            straight = 2 * R * _math.asin(_math.sqrt(a))
            c1 = port_country_vj.get(pa, '')
            c2 = port_country_vj.get(pb, '')
            f = (1.45 if c1 == 'Indonesia' and c2 == 'Indonesia'
                 else 1.40 if 'Bangladesh' in [c1, c2]
                 else 1.35 if 'Philippines' in [c1, c2]
                 else 1.25)
            return round(straight * f)

        def _geodesic_vj(lat1, lon1, lat2, lon2, n=60):
            if lat1 == lat2 and lon1 == lon2:
                return [lat1], [lon1]
            la1 = _math.radians(lat1); lo1 = _math.radians(lon1)
            la2 = _math.radians(lat2); lo2 = _math.radians(lon2)
            d = 2 * _math.asin(_math.sqrt(
                _math.sin((la2-la1)/2)**2
                + _math.cos(la1) * _math.cos(la2)
                * _math.sin((lo2-lo1)/2)**2
            ))
            if d == 0:
                return [lat1, lat2], [lon1, lon2]
            lats, lons = [], []
            for i in range(n + 1):
                f  = i / n
                A  = _math.sin((1-f)*d) / _math.sin(d)
                B  = _math.sin(f*d)     / _math.sin(d)
                x  = (A*_math.cos(la1)*_math.cos(lo1)
                      + B*_math.cos(la2)*_math.cos(lo2))
                y  = (A*_math.cos(la1)*_math.sin(lo1)
                      + B*_math.cos(la2)*_math.sin(lo2))
                z  = A*_math.sin(la1) + B*_math.sin(la2)
                lats.append(_math.degrees(_math.atan2(
                    z, _math.sqrt(x*x + y*y))))
                lons.append(_math.degrees(_math.atan2(y, x)))
            return lats, lons

        def _get_sea_route_lats_lons_vj(port_a, port_b, p_coords):
            """
            Return (lats, lons) for sea route between two ports.
            Uses real Searoute waypoints if available; falls back to geodesic arc.
            """
            try:
                waypoints = get_sea_route_coords(port_a, port_b)
                if waypoints and len(waypoints) > 2:
                    lons = [w[0] for w in waypoints]
                    lats = [w[1] for w in waypoints]
                    return lats, lons
            except Exception:
                pass
            # Fallback to geodesic arc
            if port_a in p_coords and port_b in p_coords:
                la1, lo1 = p_coords[port_a]
                la2, lo2 = p_coords[port_b]
                return _geodesic_vj(la1, lo1, la2, lo2)
            return [], []

        # ── Programme selector ────────────────────────────────────────
        hc1, hc2, hc3 = st.columns([3, 1, 1])
        with hc1:
            prog_opts_vj = [
                f"#{p['rank']}  —  ${p['total_profit']:,.0f}  —  "
                f"{p['n_voyages']} voyages  —  TCE ${p['avg_tce']:,.0f}/day"
                for p in top_progs_vj
            ]
            sel_prog_vj = st.selectbox(
                "Programme",
                range(len(top_progs_vj)),
                format_func=lambda i: prog_opts_vj[i],
                key='vj_prog_sel',
                label_visibility='collapsed',
            )
        prog_vj      = top_progs_vj[sel_prog_vj]
        legs_list_vj = prog_vj['legs']

        with hc2:
            st.metric("Annual Profit", f"${prog_vj['total_profit']:,.0f}")
        with hc3:
            try:
                eb_vj = export_programme_to_excel(
                    prog_vj, vessel_vj, prog_vj['rank']
                )
                st.download_button(
                    label="📥 Export Excel", data=eb_vj,
                    file_name=f"voyage_journey_{prog_vj['rank']}.xlsx",
                    mime=(
                        "application/vnd.openxmlformats-officedocument"
                        ".spreadsheetml.sheet"
                    ),
                    use_container_width=True,
                )
            except Exception:
                pass


        # -- Enhanced live stats with profit counter ─────────────────────
        cur_anim_voy = 0
        cur_leg_va   = legs_list_vj[0] if legs_list_vj else {}
        legs_list    = legs_list_vj
        cum_pl_va    = prog_vj['total_profit']
        cum_days_va  = sum(l.get('total_days', 0) for l in legs_list_vj)
        cur_pl_va    = cur_leg_va.get('profit_loss', cur_leg_va.get('profit', 0))
        _arc_nm_0    = _calc_nm_vj(
            cur_leg_va.get('origin_port', ''),
            cur_leg_va.get('dest_port', ''),
        )
        all_arc_nms  = [_arc_nm_0]

        st.markdown(
            f"<div style='background:linear-gradient(135deg,#1a3a5c,#2d5986);"
            f"border-radius:12px;padding:16px 20px;margin-bottom:12px'>"
            f"<div style='display:flex;align-items:center;justify-content:space-between;"
            f"flex-wrap:wrap;gap:12px'>"

            f"<div>"
            f"<div style='font-size:10px;color:#94a3b8;text-transform:uppercase;"
            f"letter-spacing:.06em'>Current Voyage</div>"
            f"<div style='font-size:14px;font-weight:600;color:white;margin-top:2px'>"
            f"{cur_leg_va.get('origin_port','')[:12]} → "
            f"{cur_leg_va.get('dest_port','')[:12]}</div>"
            f"<div style='font-size:11px;color:#94a3b8;margin-top:2px'>"
            f"{cur_leg_va.get('commodity','—')} · "
            f"{all_arc_nms[cur_anim_voy]:,} NM</div>"
            f"</div>"

            f"<div style='text-align:center'>"
            f"<div style='font-size:10px;color:#94a3b8;text-transform:uppercase;"
            f"letter-spacing:.06em'>Cumulative Profit</div>"
            f"<div style='font-size:2.2rem;font-weight:700;"
            f"color:{'#86efac' if cum_pl_va >= 0 else '#fca5a5'};"
            f"letter-spacing:-1px;margin-top:2px'>"
            f"{'+'if cum_pl_va>=0 else ''}"
            f"${abs(cum_pl_va):,.0f}</div>"
            f"<div style='font-size:10px;color:#94a3b8;margin-top:2px'>"
            f"Voyage {cur_anim_voy+1}/{len(legs_list)} · "
            f"Day {cum_days_va:.0f}/330</div>"
            f"</div>"

            f"<div style='text-align:right'>"
            f"<div style='font-size:10px;color:#94a3b8;text-transform:uppercase;"
            f"letter-spacing:.06em'>Voyage P&L</div>"
            f"<div style='font-size:1.4rem;font-weight:600;"
            f"color:{'#86efac' if cur_pl_va>=0 else '#fca5a5'};"
            f"margin-top:2px'>"
            f"{'+'if cur_pl_va>=0 else ''}${cur_pl_va:,.0f}</div>"
            f"<div style='font-size:10px;color:#94a3b8;margin-top:2px'>"
            f"TCE ${cur_pl_va/max(cur_leg_va.get('total_days',1),1):,.0f}/day</div>"
            f"</div>"

            f"</div></div>",
            unsafe_allow_html=True
        )

        # Secondary stats row
        sv1, sv2, sv3, sv4, sv5, sv6 = st.columns(6)
        sv1.metric("Route",     f"V{cur_anim_voy+1}/{len(legs_list)}")
        sv2.metric("Commodity", cur_leg_va.get('commodity', '—')[:12])
        sv3.metric("Distance",  f"{all_arc_nms[cur_anim_voy]:,} NM")
        sv4.metric(
            "Voyage P&L",
            f"{'+'if cur_pl_va>=0 else ''}${cur_pl_va:,.0f}",
            delta_color="normal" if cur_pl_va >= 0 else "inverse",
        )
        sv5.metric(
            "Annual target",
            f"${cum_pl_va/max(cum_days_va,1)*330:,.0f}",
            help="Extrapolated annual profit at current rate",
        )
        sv6.metric("Days elapsed", f"{cum_days_va:.0f}/330")

        st.markdown("---")

        # ═══════════════════════════════════════════════════════════════
        # ═══════════════════════════════════════════════════════════════
        # ZONE 2 — Dark maritime map (Plotly scattermapbox, carto-darkmatter)
        # ═══════════════════════════════════════════════════════════════

        import json as _json2

        voyage_data_vj = []
        for leg in legs_list_vj:
            op   = leg.get('origin_port', '')
            dp   = leg.get('dest_port', '')
            pl   = leg.get('profit_loss', leg.get('profit', 0))

            # Laden route — real sea routes with geodesic fallback
            lats2, lons2 = _get_sea_route_lats_lons_vj(op, dp, port_coords_vj)

            # Ballast route
            _bp = leg.get('ballast_from_port', '')
            _get_ballast_lats, _get_ballast_lons = [], []
            if _bp and _bp != op and _bp in port_coords_vj and op in port_coords_vj:
                _get_ballast_lats, _get_ballast_lons = _get_sea_route_lats_lons_vj(
                    _bp, op, port_coords_vj
                )

            voyage_data_vj.append({
                'from':         op,
                'to':           dp,
                'comm':         leg.get('commodity', ''),
                'pl':           round(pl),
                'days':         round(leg.get('total_days', 0), 1),
                'nm':           _calc_nm_vj(op, dp),
                'rate':         round(leg.get('freight_rate', 0), 2),
                'cargo':        round(leg.get('cargo_mt', 0)),
                'cum':          round(leg.get('cum_profit', 0)),
                'lats':         lats2,
                'lons':         lons2,
                'ballast_from': _bp,
                'ballast_lats': _get_ballast_lats,
                'ballast_lons': _get_ballast_lons,
                'ballast_days': round(leg.get('ballast_days', 0), 1),
                'laden_days':   round(leg.get('laden_days', 0), 1),
                'olat': port_coords_vj[op][0] if op in port_coords_vj else 0,
                'olon': port_coords_vj[op][1] if op in port_coords_vj else 0,
                'dlat': port_coords_vj[dp][0] if dp in port_coords_vj else 0,
                'dlon': port_coords_vj[dp][1] if dp in port_coords_vj else 0,
            })

        all_ports_vj2 = [
            {'name': p,
             'lat':  port_coords_vj[p][0],
             'lon':  port_coords_vj[p][1]}
            for p in (set(l.get('origin_port', '') for l in legs_list_vj)
                      | set(l.get('dest_port', '') for l in legs_list_vj))
            if p and p in port_coords_vj
        ]
        if all_ports_vj2:
            _clat2 = sum(p['lat'] for p in all_ports_vj2) / len(all_ports_vj2)
            _clon2 = sum(p['lon'] for p in all_ports_vj2) / len(all_ports_vj2)
        else:
            _clat2, _clon2 = 8.0, 108.0

        voyage_json2 = _json2.dumps(voyage_data_vj)
        ports_json2  = _json2.dumps(all_ports_vj2)
        centre_json2 = _json2.dumps({'lat': _clat2, 'lon': _clon2})

        # ── Dark Plotly scattermapbox map ─────────────────────────────
        MARITIME_HTML = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#0a1628; font-family:-apple-system,sans-serif; }}
#map {{ width:100%; height:480px; border-radius:10px; overflow:hidden; }}
.controls {{ display:flex; align-items:center; gap:8px; margin:8px 0 4px; flex-wrap:wrap; }}
.btn {{ background:#1a3a5c; color:white; border:none; padding:7px 16px;
        border-radius:8px; font-size:12px; cursor:pointer; min-width:80px; }}
.btn:hover {{ background:#2d5986; }}
.btn-sec {{ background:#0f172a; color:#94a3b8; border:1px solid #334155;
             padding:7px 14px; border-radius:8px; font-size:12px; cursor:pointer; }}
.btn-sec:hover {{ background:#1e293b; }}
select {{ padding:6px 10px; border-radius:8px; border:1px solid #334155;
          font-size:12px; background:#1e293b; color:#e2e8f0; cursor:pointer; }}
.badge {{ background:#1e293b; color:#7dd3fc; padding:6px 12px; border-radius:8px;
          font-size:12px; font-weight:500; border:1px solid #334155; white-space:nowrap; }}
.stats {{ display:grid; grid-template-columns:repeat(7,1fr); gap:5px; margin-top:4px; }}
.stat {{ background:#1e293b; border-radius:8px; padding:6px 10px; border:1px solid #334155; }}
.stat-lbl {{ font-size:9px; color:#64748b; text-transform:uppercase; letter-spacing:.05em; }}
.stat-val {{ font-size:12px; font-weight:500; color:#e2e8f0; margin-top:2px;
             white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
</style>
</head>
<body>
<div id="map"></div>
<div class="controls">
  <button class="btn" id="btnPlay" onclick="togglePlay()">&#9654; Play</button>
  <button class="btn-sec" onclick="resetAnim()">&#8635; Reset</button>
  <select id="spdSel" onchange="setSpd(this.value)">
    <option value="120">Slow</option>
    <option value="60" selected>Normal</option>
    <option value="30">Fast</option>
    <option value="15">Very Fast</option>
  </select>
  <input type="range" id="scrub" min="0" max="100" value="0" step="1"
         style="flex:1;min-width:80px;accent-color:#3b82f6">
  <span class="badge" id="voyBadge">V 1 / —</span>
</div>
<div class="stats">
  <div class="stat"><div class="stat-lbl">Route</div>
    <div class="stat-val" id="sRoute">—</div></div>
  <div class="stat"><div class="stat-lbl">Phase</div>
    <div class="stat-val" id="sPhase">—</div></div>
  <div class="stat"><div class="stat-lbl">Commodity</div>
    <div class="stat-val" id="sComm">—</div></div>
  <div class="stat"><div class="stat-lbl">Distance</div>
    <div class="stat-val" id="sNm">—</div></div>
  <div class="stat"><div class="stat-lbl">Voyage P&amp;L</div>
    <div class="stat-val" id="sPl">—</div></div>
  <div class="stat"><div class="stat-lbl">Cumulative</div>
    <div class="stat-val" id="sCum">$0</div></div>
  <div class="stat"><div class="stat-lbl">Days elapsed</div>
    <div class="stat-val" id="sDays">0 d</div></div>
</div>
<script src="https://cdn.jsdelivr.net/npm/plotly.js-dist@2.26.0/plotly.min.js"></script>
<script>
const VOYAGES   = {voyage_json2};
const ALL_PORTS = {ports_json2};
const CENTRE    = {centre_json2};

const traces = [];

// 1. Background port dots
traces.push({{
  type:'scattermapbox',
  lat: ALL_PORTS.map(p => p.lat),
  lon: ALL_PORTS.map(p => p.lon),
  mode:'markers',
  marker:{{size:5, color:'#64748b', opacity:0.5}},
  hoverinfo:'skip', showlegend:false, name:'bg_ports'
}});

// 2. Background voyage arcs (ballast grey + laden coloured)
VOYAGES.forEach((v, vi) => {{
  if (v.ballast_lats && v.ballast_lats.length > 1) {{
    traces.push({{
      type:'scattermapbox',
      lat: v.ballast_lats, lon: v.ballast_lons, mode:'lines',
      line:{{width:1.5, color:'rgba(148,163,184,0.25)'}},
      opacity:1, hoverinfo:'skip', showlegend:false, name:'ballast_'+vi
    }});
  }}
  if (!v.lats.length) return;
  const col = v.pl >= 0 ? '#22c55e' : '#ef4444';
  traces.push({{
    type:'scattermapbox',
    lat: v.lats, lon: v.lons, mode:'lines',
    line:{{width:2, color:col}}, opacity:0.22,
    hoverinfo:'skip', showlegend:false, name:'arc_'+vi
  }});
}});

// 3. Port markers
const portCoords = {{}};
ALL_PORTS.forEach(p => {{ portCoords[p.name] = {{lat:p.lat, lon:p.lon}}; }});
const portsSeen = {{}};
VOYAGES.forEach(v => {{
  if (!portsSeen[v.from]) portsSeen[v.from] = 'load';
  if (!portsSeen[v.to])   portsSeen[v.to]   = 'disch';
}});
const loadNames  = Object.keys(portsSeen).filter(n => portsSeen[n]==='load'  && portCoords[n]);
const dischNames = Object.keys(portsSeen).filter(n => portsSeen[n]==='disch' && portCoords[n]);

traces.push({{
  type:'scattermapbox',
  lat: loadNames.map(n => portCoords[n].lat),
  lon: loadNames.map(n => portCoords[n].lon),
  mode:'markers+text', text: loadNames,
  marker:{{size:9, color:'#3b82f6', opacity:0.85}},
  textposition:'top right', textfont:{{size:9, color:'#cbd5e1'}},
  hoverinfo:'text', showlegend:false, name:'load_ports'
}});
traces.push({{
  type:'scattermapbox',
  lat: dischNames.map(n => portCoords[n].lat),
  lon: dischNames.map(n => portCoords[n].lon),
  mode:'markers+text', text: dischNames,
  marker:{{size:9, color:'#dc2626', opacity:0.85}},
  textposition:'top right', textfont:{{size:9, color:'#cbd5e1'}},
  hoverinfo:'text', showlegend:false, name:'disch_ports'
}});

// 4. Active traces (initially empty, updated by Plotly.restyle)
const ACTIVE_BALLAST_IDX = traces.length;
traces.push({{
  type:'scattermapbox', lat:[], lon:[], mode:'lines',
  line:{{width:3, color:'rgba(148,163,184,0.85)'}},
  opacity:1, hoverinfo:'skip', showlegend:false, name:'active_ballast'
}});

const ACTIVE_ARC_IDX = traces.length;
traces.push({{
  type:'scattermapbox', lat:[], lon:[], mode:'lines',
  line:{{width:5, color:'#f59e0b'}},
  opacity:1, hoverinfo:'skip', showlegend:false, name:'active_arc'
}});

// 5. Vessel marker
const VESSEL_IDX = traces.length;
traces.push({{
  type:'scattermapbox',
  lat:[CENTRE.lat], lon:[CENTRE.lon], mode:'markers',
  marker:{{size:14, color:'#f59e0b', symbol:'circle'}},
  hoverinfo:'skip', showlegend:false, name:'vessel'
}});

const layout = {{
  mapbox:{{
    style:'carto-darkmatter',
    zoom:4.2,
    center:{{lat:CENTRE.lat, lon:CENTRE.lon}}
  }},
  height:480,
  margin:{{l:0, r:0, t:0, b:0}},
  paper_bgcolor:'rgba(10,22,40,0)',
  plot_bgcolor:'rgba(10,22,40,0)',
  showlegend:false,
  hoverlabel:{{bgcolor:'#1e293b', bordercolor:'#334155',
               font:{{size:12, color:'#e2e8f0'}}}},
}};

Plotly.newPlot('map', traces, layout, {{
  responsive:true, displayModeBar:false, scrollZoom:true
}});

// Animation state
let playing=false, spd=60, curV=0, t=0, cumDays=0;
let phase='ballast';
let lastTs=null, raf=null;

function setSpd(v) {{ spd=parseInt(v); }}

function togglePlay() {{
  playing=!playing;
  document.getElementById('btnPlay').textContent = playing ? '&#9646;&#9646; Pause' : '&#9654; Play';
  if (playing && !raf) {{ lastTs=null; raf=requestAnimationFrame(tick); }}
}}

function resetAnim() {{
  playing=false;
  document.getElementById('btnPlay').textContent='&#9654; Play';
  if(raf){{ cancelAnimationFrame(raf); raf=null; }}
  curV=0; t=0; cumDays=0; phase='ballast';
  Plotly.restyle('map', {{lat:[[]], lon:[[]]}}, [ACTIVE_BALLAST_IDX, ACTIVE_ARC_IDX]);
  Plotly.restyle('map', {{lat:[[CENTRE.lat]], lon:[[CENTRE.lon]]}}, [VESSEL_IDX]);
  document.getElementById('scrub').value=0;
  updateHUD();
}}

function tick(ts) {{
  if(!lastTs) lastTs=ts;
  const dt=(ts-lastTs)/1000; lastTs=ts;
  if(playing) advance(dt);
  updateHUD();
  if(playing) raf=requestAnimationFrame(tick);
  else raf=null;
}}

function advance(dt) {{
  const v=VOYAGES[curV]; if(!v) return;
  const hasBallast = v.ballast_lats && v.ballast_lats.length > 1;
  const phaseDays  = phase==='ballast' ? Math.max(v.ballast_days||0, 0.3)
                                        : Math.max(v.laden_days || v.days || 1, 0.3);
  t += (dt * 1000) / (spd * phaseDays);
  cumDays += dt * phaseDays / phaseDays;  // increment by actual dt

  if (t >= 1) {{
    t = 0;
    if (phase==='ballast' && hasBallast) {{
      phase = 'laden';
    }} else {{
      curV++;
      phase = 'ballast';
      if (curV >= VOYAGES.length) {{
        curV=VOYAGES.length-1; t=1; playing=false;
        document.getElementById('btnPlay').textContent='&#9654; Play';
        if(raf){{ cancelAnimationFrame(raf); raf=null; }}
      }}
    }}
  }}

  const progress = Math.min(t, 1);
  const v2 = VOYAGES[curV]; if(!v2) return;
  const isBallastPhase = (phase==='ballast');

  // Update active ballast trace
  if (v2.ballast_lats && v2.ballast_lats.length > 1 && isBallastPhase) {{
    const end = Math.floor(progress * v2.ballast_lats.length);
    Plotly.restyle('map', {{
      lat: [v2.ballast_lats.slice(0, end+1)],
      lon: [v2.ballast_lons.slice(0, end+1)]
    }}, [ACTIVE_BALLAST_IDX]);
  }} else {{
    Plotly.restyle('map', {{lat:[[]], lon:[[]]}}, [ACTIVE_BALLAST_IDX]);
  }}

  // Update active laden trace
  if (!isBallastPhase && v2.lats.length) {{
    const end = Math.floor(progress * v2.lats.length);
    Plotly.restyle('map', {{
      lat: [v2.lats.slice(0, end+1)],
      lon: [v2.lons.slice(0, end+1)]
    }}, [ACTIVE_ARC_IDX]);
  }} else {{
    Plotly.restyle('map', {{lat:[[]], lon:[[]]}}, [ACTIVE_ARC_IDX]);
  }}

  // Update vessel position
  const arcLat = isBallastPhase ? v2.ballast_lats : v2.lats;
  const arcLon = isBallastPhase ? v2.ballast_lons : v2.lons;
  if (arcLat && arcLat.length) {{
    const idx = Math.min(Math.floor(progress * arcLat.length), arcLat.length-1);
    Plotly.restyle('map', {{lat:[[arcLat[idx]]], lon:[[arcLon[idx]]]}}, [VESSEL_IDX]);
  }}

  // Scrub bar
  const overall = (curV + (isBallastPhase ? 0 : 0.5) + progress*0.5) / VOYAGES.length;
  document.getElementById('scrub').value = Math.round(overall*100);
}}

function updateHUD() {{
  const v = VOYAGES[curV] || VOYAGES[VOYAGES.length-1];
  const cumPl = VOYAGES.slice(0, curV).reduce((s,x) => s+x.pl, 0);
  const isBallastPhase = (phase==='ballast');

  document.getElementById('sRoute').textContent =
    v.from.split(' ')[0] + ' → ' + v.to.split(' ')[0];

  const phaseEl = document.getElementById('sPhase');
  phaseEl.textContent = isBallastPhase ? '□ Ballast' : '▦ Laden';
  phaseEl.style.color = isBallastPhase ? '#94a3b8' : '#4ade80';

  document.getElementById('sComm').textContent = v.comm || '—';
  document.getElementById('sNm').textContent   = (v.nm||0).toLocaleString() + ' NM';
  document.getElementById('sPl').textContent   = (v.pl>=0?'+':'') + '$' + (v.pl||0).toLocaleString();
  document.getElementById('sCum').textContent  = (cumPl>=0?'+':'') + '$' + cumPl.toLocaleString();
  document.getElementById('sDays').textContent = Math.round(cumDays) + ' d';
  document.getElementById('voyBadge').textContent = 'V ' + (curV+1) + ' / ' + VOYAGES.length;
}}

// Scrub bar manual seek
document.getElementById('scrub').addEventListener('input', function(e) {{
  if(playing){{ playing=false; document.getElementById('btnPlay').textContent='&#9654; Play';
                if(raf){{ cancelAnimationFrame(raf); raf=null; }} }}
  const pct = parseInt(e.target.value) / 100;
  curV  = Math.min(Math.floor(pct * VOYAGES.length), VOYAGES.length-1);
  t=0; phase='ballast'; cumDays=0;
  Plotly.restyle('map', {{lat:[[]], lon:[[]]}}, [ACTIVE_BALLAST_IDX, ACTIVE_ARC_IDX]);
  updateHUD();
}});

updateHUD();
</script>
</body>
</html>"""


        # ── Elements BEFORE canvas ───────────────────────────────────────
        legs_vj = legs_list_vj

        # Element 1 — Voyage slider
        sl_col1, sl_col2 = st.columns([5, 1])
        with sl_col1:
            vj_slider = st.slider(
                "Voyage",
                min_value=1,
                max_value=len(legs_vj),
                value=1,
                step=1,
                key='vj_voyage_slider',
                label_visibility='collapsed',
            )
        with sl_col2:
            st.markdown(
                f"<div style='background:#1a3a5c;color:white;text-align:center;"
                f"padding:6px 10px;border-radius:8px;font-size:13px;font-weight:500'>"
                f"V {vj_slider} / {len(legs_vj)}</div>",
                unsafe_allow_html=True
            )

        # Element 2 — Stats row
        sel_vj_leg = legs_vj[vj_slider - 1]
        sel_pl     = sel_vj_leg.get('profit_loss', sel_vj_leg.get('profit', 0))
        cum_pl_vj  = sum(
            l.get('profit_loss', l.get('profit', 0))
            for l in legs_vj[:vj_slider]
        )
        sel_dist   = sel_vj_leg.get('laden_nm', sel_vj_leg.get('distance_nm', 0))
        sel_comm   = sel_vj_leg.get('commodity', '—')
        sel_orig   = sel_vj_leg.get('origin_port', '—')
        sel_dest   = sel_vj_leg.get('dest_port', '—')
        sel_days   = sum(l.get('total_days', 0) for l in legs_vj[:vj_slider])

        sc1, sc2, sc3, sc4, sc5, sc6 = st.columns(6)
        sc1.metric("Route",       f"{sel_orig.split()[0]} → {sel_dest.split()[0]}")
        sc2.metric("Commodity",   sel_comm[:16])
        sc3.metric("Distance",    f"{sel_dist:,.0f} NM")
        sc4.metric("Voyage P&L",
                   f"{'+'if sel_pl>=0 else ''}${sel_pl:,.0f}",
                   delta_color="normal" if sel_pl >= 0 else "inverse")
        sc5.metric("Cumulative",  f"+${cum_pl_vj:,.0f}")
        sc6.metric("Days Elapsed", f"{sel_days:.0f} d")

        # ── Canvas ───────────────────────────────────────────────────────
        st.components.v1.html(MARITIME_HTML, height=570, scrolling=False)

        # ── Elements AFTER canvas ─────────────────────────────────────────

        # Element 3 — Voyage schedule list
        st.markdown(
            "<div style='font-size:11px;color:#64748b;margin-bottom:6px'>"
            "Voyage schedule — click to jump</div>",
            unsafe_allow_html=True
        )
        COMM_COLORS_VJ = {
            'Steam Coal':           '#475569',
            'Steels':               '#3b82f6',
            'Palm Kernel Expeller': '#16a34a',
            'Nickel Ore':           '#ea580c',
            'Fertilizers':          '#7c3aed',
            'Sugar':                '#ca8a04',
            'Clinker':              '#dc2626',
            'Coking Coal':          '#374151',
        }
        for i, leg in enumerate(legs_vj):
            pl_l   = leg.get('profit_loss', leg.get('profit', 0))
            comm_l = leg.get('commodity', '')
            orig_l = leg.get('origin_port', '')[:12]
            dest_l = leg.get('dest_port', '')[:12]
            days_l = leg.get('total_days', 0)
            sign_l = '+' if pl_l >= 0 else ''
            pl_col_l = '#166534' if pl_l >= 0 else '#991b1b'
            pl_bg_l  = '#dcfce7' if pl_l >= 0 else '#fee2e2'

            c1, c2, c3 = st.columns([3, 2, 1])
            with c1:
                st.markdown(
                    f"<div style='font-size:12px;padding:3px 0'>"
                    f"<span style='color:#94a3b8;margin-right:6px'>{i+1}</span>"
                    f"{orig_l} → {dest_l}</div>",
                    unsafe_allow_html=True
                )
            with c2:
                cc = COMM_COLORS_VJ.get(comm_l, '#64748b')
                st.markdown(
                    f"<span style='background:{cc}22;color:{cc};"
                    f"font-size:10px;padding:2px 7px;border-radius:8px'>"
                    f"{comm_l[:18]}</span>",
                    unsafe_allow_html=True
                )
            with c3:
                st.markdown(
                    f"<div style='text-align:right'>"
                    f"<span style='font-size:11px;background:{pl_bg_l};"
                    f"color:{pl_col_l};padding:2px 7px;border-radius:8px'>"
                    f"{sign_l}${abs(pl_l)/1000:.0f}k</span>"
                    f"<div style='font-size:10px;color:#94a3b8;"
                    f"text-align:right'>{days_l:.1f}d</div></div>",
                    unsafe_allow_html=True
                )

        # Element 4 — Legend + MarineTraffic link
        leg1, leg2, leg3, leg4, leg5 = st.columns(5)
        leg1.markdown(
            "<div style='display:flex;align-items:center;gap:4px'>"
            "<div style='width:10px;height:10px;border-radius:50%;"
            "background:#f59e0b'></div>"
            "<span style='font-size:11px;color:#475569'>Vessel</span>"
            "</div>", unsafe_allow_html=True
        )
        leg2.markdown(
            "<div style='display:flex;align-items:center;gap:4px'>"
            "<div style='width:10px;height:10px;border-radius:50%;"
            "background:#1d4ed8'></div>"
            "<span style='font-size:11px;color:#475569'>Load port</span>"
            "</div>", unsafe_allow_html=True
        )
        leg3.markdown(
            "<div style='display:flex;align-items:center;gap:4px'>"
            "<div style='width:10px;height:10px;border-radius:50%;"
            "background:#dc2626'></div>"
            "<span style='font-size:11px;color:#475569'>Discharge</span>"
            "</div>", unsafe_allow_html=True
        )
        leg4.markdown(
            "<div style='display:flex;align-items:center;gap:4px'>"
            "<div style='width:22px;height:3px;background:#22c55e'></div>"
            "<span style='font-size:11px;color:#475569'>Profitable</span>"
            "</div>", unsafe_allow_html=True
        )
        leg5.markdown(
            "<div style='text-align:right'>"
            "<a href='https://www.marinetraffic.com' "
            "style='font-size:11px;color:#0369a1;text-decoration:none'>"
            "MarineTraffic ↗</a></div>",
            unsafe_allow_html=True
        )

# ─── TAB 7: PORT VALIDATION ──────────────────────────────────────────────────
with tabs[6]:
    st.markdown("### ⚓ Port Validation Report")
    st.markdown(
        "Shows all database ports filtered against vessel physical dimensions. "
        "Every access decision is shown for full transparency."
    )

    from data.port_restrictions import PORT_SUITABILITY, NOT_SUITABLE_PORTS, RESTRICTED_PORTS

    _pv_vessel = st.session_state.get('vessel')
    vessel_draft   = _pv_vessel.draft_laden   if _pv_vessel else 9.5
    vessel_draft_b = _pv_vessel.draft_ballast if _pv_vessel else 5.5
    vessel_loa     = _pv_vessel.loa           if _pv_vessel else 150.0
    vessel_beam    = _pv_vessel.beam          if _pv_vessel else 24.0

    # Summary funnel metrics
    total_db       = 769
    sea_region     = 378
    far_east_added = 65
    accessible = sum(1 for v in PORT_SUITABILITY.values()
                     if v["status"] in ("EXCELLENT", "GOOD"))
    restricted = sum(1 for v in PORT_SUITABILITY.values()
                     if v["status"] == "RESTRICTED")
    blocked    = sum(1 for v in PORT_SUITABILITY.values()
                     if v["status"] == "NOT_SUITABLE")

    pvc1, pvc2, pvc3, pvc4, pvc5 = st.columns(5)
    pvc1.metric("Total database",    total_db,
                help="Global maritime port database")
    pvc2.metric("SEA + Far East",    sea_region + far_east_added,
                help=f"SEA ({sea_region}) + China/Japan/Korea/TW/HK ({far_east_added})")
    pvc3.metric("✅ Active",          accessible,
                help="EXCELLENT + GOOD — vessel enters fully laden")
    pvc4.metric("⚠️ Restricted",     restricted,
                help="Conditional entry — tidal, draft limits")
    pvc5.metric("❌ Eliminated",      blocked,
                help="Vessel cannot enter under any condition")

    st.markdown("---")

    _PV_REGION_MAP = {
        "China":          {"Shanghai","Lianyungang","Meizhou","Qinzhou","Rizhao","Machong",
                           "Saiqi","Yangjiang","Tieshan","Lanshan","Nantong","Taicang",
                           "Nanjing","Chaozhou","Haimen (Guangdong Province)","Yuhuan",
                           "Xiamen","Gaolan","Shanwei","Fangcheng","Luoyuanwan","Guangzhou",
                           "Zhanjiang","Yangpu (Hainan)","Ningde","Kemen","Caofeidian",
                           "Weifang","Changzhou","Jinzhou","Jiazi","Bayuquan","Zhenjiang",
                           "Ningbo (incl Zhoushan)","Huanghua","Dalian","Fuzhou (incl Fuqing)",
                           "Huizhou","Zhangjiagang","Dongguan"},
        "Japan":          {"Tachibana","Hekinan","Kawanoe (Iyomishima)","Toyama","Sakaiminato",
                           "Hachinohe","Kobe","Tokuyama","Matsuura","Tonda","Nagoya",
                           "Yokohama","Osaka","Kashima","Ishinomaki"},
        "Korea South":    {"Kwangyang","Dangjin","Hosan","Samcheon Po","Incheon","Boryeong",
                           "Daesan","Gunsan","Ulsan","Pyeongtaek"},
        "Taiwan/HK":      {"Taichung","Kaohsiung","Lingkou","Ho Ping","Hong Kong"},
        "Bangladesh":     {"Chittagong","Matarbari","Mongla"},
        "Southeast Asia": None,  # everything else
    }

    pv_sf, pv_rf, pv_nf = st.columns([1, 1, 2])
    with pv_sf:
        status_filter = st.selectbox(
            "Filter by status",
            ["All", "✅ EXCELLENT", "🔵 GOOD", "⚠️ RESTRICTED", "❌ NOT SUITABLE"],
            key="pv_status_filter",
        )
    with pv_rf:
        region_filter = st.selectbox(
            "Filter by region",
            ["All regions", "Southeast Asia", "China", "Japan",
             "Korea South", "Taiwan/HK", "Bangladesh"],
            key="pv_region_filter",
        )
    with pv_nf:
        country_filter = st.text_input(
            "Search port name", key="pv_country_filter",
            placeholder="e.g. Samarinda, Bangkok, Rizhao, Nagoya…"
        )

    # Build table rows
    _status_map = {
        "EXCELLENT":    "✅ EXCELLENT",
        "GOOD":         "🔵 GOOD",
        "RESTRICTED":   "⚠️ RESTRICTED",
        "NOT_SUITABLE": "❌ BLOCKED",
    }
    _filter_map = {
        "✅ EXCELLENT":   "EXCELLENT",
        "🔵 GOOD":        "GOOD",
        "⚠️ RESTRICTED":  "RESTRICTED",
        "❌ NOT SUITABLE": "NOT_SUITABLE",
    }
    rows_pv = []
    for port, info in sorted(PORT_SUITABILITY.items()):
        status = info["status"]
        if status_filter != "All" and status != _filter_map.get(status_filter, ""):
            continue
        if country_filter and country_filter.lower() not in port.lower():
            continue
        # Region filter
        if region_filter != "All regions":
            _rf_key = region_filter if region_filter != "Bangladesh" else "Bangladesh"
            _rf_ports = _PV_REGION_MAP.get(_rf_key)
            if _rf_ports is not None:
                if port not in _rf_ports:
                    continue
            else:
                # "Southeast Asia" = all ports NOT in any Far East group
                _all_fe = (
                    _PV_REGION_MAP["China"] | _PV_REGION_MAP["Japan"] |
                    _PV_REGION_MAP["Korea South"] | _PV_REGION_MAP["Taiwan/HK"] |
                    _PV_REGION_MAP["Bangladesh"]
                )
                if port in _all_fe:
                    continue

        max_draft = info.get("max_draft", 99.0)
        if status == "NOT_SUITABLE":
            reason = (f"❌ Max draft {max_draft}m — vessel needs "
                      f"{vessel_draft}m laden. Physically impossible.")
        elif status == "RESTRICTED":
            if max_draft < vessel_draft:
                reason = (f"⚠️ Max draft {max_draft}m < vessel laden "
                          f"draft {vessel_draft}m. Ballast/partial entry only.")
            else:
                penalty = RESTRICTED_PORTS.get(port, {})
                from data.port_restrictions import TIDAL_PENALTY_DAYS
                td = TIDAL_PENALTY_DAYS.get(port, 0.5)
                reason = f"⚠️ Tidal/river restrictions. Waiting penalty: +{td:.1f} days."
        else:
            reason = "✅ Fully accessible — vessel enters laden"

        rows_pv.append({
            "Port":      port,
            "Status":    _status_map.get(status, status),
            "Max Draft": f"{max_draft}m",
            "Decision":  reason,
            "Notes":     info.get("notes", ""),
        })

    df_pv = pd.DataFrame(rows_pv)
    if df_pv.empty:
        st.info("No ports match the current filter.")
    else:
        st.dataframe(
            df_pv,
            use_container_width=True,
            hide_index=True,
            height=520,
            column_config={
                "Port":      st.column_config.TextColumn("Port",       width="medium"),
                "Status":    st.column_config.TextColumn("Status",     width="small"),
                "Max Draft": st.column_config.TextColumn("Max Draft",  width="small"),
                "Decision":  st.column_config.TextColumn(
                    "Access / Elimination Reason", width="large"),
                "Notes":     st.column_config.TextColumn("Notes",      width="medium"),
            },
        )

    st.caption(
        f"Vessel specs: Draft laden {vessel_draft}m | "
        f"Ballast {vessel_draft_b}m | LOA {vessel_loa}m | Beam {vessel_beam}m"
    )

