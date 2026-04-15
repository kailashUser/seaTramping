"""
SEA Tramping Simulation Engine V2
- Exact costing model: dual fuel (LSFO + MGO), brokerage, insurance proration
- Network graph analysis via NetworkX (centrality, community detection)
- Greedy constructive heuristic + 2-opt local search
- Monte Carlo stochastic perturbation
- NumPy-vectorised fast leg evaluation targeting 200+ iter/sec
- Voyage dependency cascade recalculation for What-If analysis
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
import time

try:
    import networkx as nx
    HAS_NX = True
except ImportError:
    HAS_NX = False

try:
    from data.port_restrictions import (
        is_port_blocked,
        get_tidal_penalty,
        NOT_SUITABLE_PORTS,
        RESTRICTED_PORTS,
        DISCHARGE_BLOCKED_PORTS,
    )
    HAS_PORT_RESTRICTIONS = True
except ImportError:
    HAS_PORT_RESTRICTIONS = False
    NOT_SUITABLE_PORTS = set()
    RESTRICTED_PORTS = {}
    DISCHARGE_BLOCKED_PORTS = {}
    def is_port_blocked(p): return False
    def get_tidal_penalty(p): return 0.0

try:
    from data.cargo_intelligence import (
        get_cleaning_cost,
        get_backhaul_penalty,
        get_seasonal_factor,
    )
    HAS_CARGO_INTEL = True
except ImportError:
    HAS_CARGO_INTEL = False
    def get_cleaning_cost(a, b): return {"grade": "G", "days": 0.0, "cost": 0}
    def get_backhaul_penalty(c): return 1.0
    def get_seasonal_factor(c, m): return 1.0


# ─── VESSEL & SIM CONFIG ──────────────────────────────────────────────────────

@dataclass
class VesselConfig:
    dwt: float = 17556
    dwcc: float = 15000                # Deadweight Cargo Capacity (max cargo MT)
    speed_laden_knots: float = 11.0
    speed_ballast_knots: float = 11.5
    laden_draft_m: float = 8.5
    charter_hire_day: float = 9000.0
    insurance_annual: float = 16000.0
    lsfo_price_mt: float = 560.0
    mgo_price_mt: float = 780.0
    brokerage_pct: float = 0.0375
    ad_com_pct: float = 0.0
    operating_days_year: int = 330
    other_costs_per_voyage: float = 1000.0
    demurrage_per_voyage: float = 12190.0
    # LSFO consumption rates MT/day by operating condition
    lsfo_maneuvering: float = 6.75
    lsfo_port: float = 5.0
    lsfo_idle: float = 1.5
    lsfo_ballast: float = 13.5
    lsfo_laden: float = 13.5
    # MGO consumption rates MT/day by operating condition
    mgo_maneuvering: float = 0.75
    mgo_port: float = 0.5
    mgo_idle: float = 1.5
    mgo_ballast: float = 1.5
    mgo_laden: float = 1.5
    # Legacy fields kept for backward compat
    fuel_laden_mt_day: float = 13.5
    fuel_ballast_mt_day: float = 13.5
    bunker_price_mt: float = 560.0
    min_cargo_pct: float = 1.0         # always full DWCC
    # Physical dimensions — used for port access validation
    draft_laden:   float = 9.5         # metres, laden condition
    draft_ballast: float = 5.5         # metres, ballast condition
    loa:           float = 150.0       # metres, length overall
    beam:          float = 24.0        # metres, beam


@dataclass
class SimConfig:
    n_iterations: int = 10000
    algorithm: str = 'hybrid'          # 'monte_carlo', 'greedy', 'hybrid'
    exploration_pct: float = 0.20
    informed_pct: float = 0.50
    exploitation_pct: float = 0.30
    freight_volatility: float = 0.15
    bunker_volatility: float = 0.10
    congestion_volatility: float = 0.30
    temperature_explore: float = 5.0
    temperature_informed: float = 2.0
    temperature_exploit: float = 0.5
    n_workers: int = 1
    top_n_programmes: int = 100
    local_search_passes: int = 2       # 2-opt improvement passes per greedy solution
    random_seed: int | None = None
    # Distribution type
    dist_type: str = 'normal'        # 'normal' or 'triangular'
    # Triangular bounds (multipliers on base value, 1.0 = base)
    freight_min:  float = 0.70
    freight_mode: float = 1.00
    freight_max:  float = 1.40
    bunker_min:   float = 0.75
    bunker_mode:  float = 1.00
    bunker_max:   float = 1.60
    cong_min:     float = 0.40
    cong_mode:    float = 1.00
    cong_max:     float = 2.00


# ─── VOYAGE DATA STRUCTURES ──────────────────────────────────────────────────

@dataclass
class VoyageLeg:
    """Full-detail voyage leg matching company spreadsheet columns."""
    # Routing
    origin_id: int
    dest_id: int
    origin_port: str
    dest_port: str
    ballast_from_port: str = ''
    # Cargo
    commodity: str = ''
    category: str = ''
    cargo_mt: float = 0.0
    freight_rate: float = 0.0
    # Distances
    ballast_nm: float = 0.0
    laden_nm: float = 0.0
    # Revenue breakdown
    gross_freight: float = 0.0
    brokerage: float = 0.0
    net_income: float = 0.0
    # Time components (days)
    maneuver_days: float = 0.503333
    loading_days: float = 0.0
    discharge_days: float = 0.0
    port_days: float = 0.0
    idle_days: float = 0.0
    ballast_days: float = 0.0
    laden_days: float = 0.0
    total_days: float = 0.0
    # Bunker detail
    lsfo_mt: float = 0.0
    mgo_mt: float = 0.0
    lsfo_cost: float = 0.0
    mgo_cost: float = 0.0
    bunker_cost: float = 0.0
    # Cost breakdown
    charter_hire: float = 0.0
    port_costs: float = 0.0
    load_port_nav: float = 0.0
    load_port_steve: float = 0.0
    disch_port_nav: float = 0.0
    disch_port_steve: float = 0.0
    insurance: float = 0.0
    other_costs: float = 0.0
    total_expenses: float = 0.0
    # P&L
    profit_loss: float = 0.0
    profit_per_day: float = 0.0
    profit_per_mt: float = 0.0
    # Cumulative (filled during programme assembly)
    cum_days: float = 0.0
    cum_profit: float = 0.0
    # Legacy aliases (kept for backward compat with Tab 4/5)
    revenue: float = 0.0
    total_cost: float = 0.0
    profit: float = 0.0
    tce: float = 0.0
    distance_nm: float = 0.0
    ballast_distance_nm: float = 0.0
    sailing_days_laden: float = 0.0
    sailing_days_ballast: float = 0.0
    load_days: float = 0.0
    disch_days: float = 0.0
    load_cong_days: float = 0.0
    disch_cong_days: float = 0.0
    congestion_days: float = 0.0
    stevedoring: float = 0.0
    fuel_cost_laden: float = 0.0
    fuel_cost_ballast: float = 0.0
    load_port_charges: float = 0.0
    disch_port_charges: float = 0.0
    load_handling_cost: float = 0.0
    disch_handling_cost: float = 0.0
    charter_hire_cost: float = 0.0
    # Two-phase breakdown
    ballast_phase:      dict = field(default_factory=dict)
    laden_phase:        dict = field(default_factory=dict)
    ballast_ratio:      float = 0.0
    ballast_cost_total: float = 0.0


@dataclass
class VoyageProgramme:
    legs: List[VoyageLeg] = field(default_factory=list)
    total_revenue: float = 0.0
    total_cost: float = 0.0
    total_profit: float = 0.0
    total_days: float = 0.0
    total_cargo_mt: float = 0.0
    n_voyages: int = 0
    utilisation_pct: float = 0.0
    avg_tce: float = 0.0
    ports_visited: set = field(default_factory=set)
    commodities_carried: set = field(default_factory=set)
    ebitda: float = 0.0
    algorithm: str = 'monte_carlo'


# ─── EXACT COSTING MODEL ─────────────────────────────────────────────────────

MANEUVER_DAYS = 0.503333  # fixed: 0.1667 × 3 port movements


def cost_voyage_exact(
    cargo_mt: float,
    freight_rate: float,
    laden_nm: float,
    ballast_nm: float,
    load_rate_mt_day: float,
    disch_rate_mt_day: float,
    load_port_nav: float,
    load_port_steve: float,
    disch_port_nav: float,
    disch_port_steve: float,
    vessel: VesselConfig,
    lsfo_price: Optional[float] = None,
    mgo_price: Optional[float] = None,
    load_cong_days: float = 0.0,
    disch_cong_days: float = 0.0,
    load_steve_per_mt: float = 0.0,
    disch_steve_per_mt: float = 0.0,
) -> dict:
    """
    Exact voyage cost model matching company spreadsheet.
    Returns a dict with full P&L breakdown.
    """
    if lsfo_price is None:
        lsfo_price = vessel.lsfo_price_mt
    if mgo_price is None:
        mgo_price = vessel.mgo_price_mt

    # ── Revenue ──────────────────────────────────────────────────────────────
    gross_freight = freight_rate * cargo_mt
    brokerage = vessel.brokerage_pct * gross_freight
    ad_com = vessel.ad_com_pct * gross_freight
    net_income = gross_freight - brokerage - ad_com

    # ── Time ─────────────────────────────────────────────────────────────────
    maneuver_days = MANEUVER_DAYS
    loading_days = cargo_mt / load_rate_mt_day if load_rate_mt_day > 0 else 0.0
    discharge_days = cargo_mt / disch_rate_mt_day if disch_rate_mt_day > 0 else 0.0
    port_days = loading_days + discharge_days
    idle_days = min(0.35 * port_days, 1.5)
    ballast_days = ballast_nm / (vessel.speed_ballast_knots * 24.0) if ballast_nm > 0 else 0.0
    laden_days = laden_nm / (vessel.speed_laden_knots * 24.0) if laden_nm > 0 else 0.0
    total_cong_days = max(0.0, load_cong_days) + max(0.0, disch_cong_days)
    total_days = maneuver_days + loading_days + idle_days + discharge_days + ballast_days + laden_days + total_cong_days

    if total_days <= 0:
        return None

    # ── Bunkers ──────────────────────────────────────────────────────────────
    lsfo_mt = (
        vessel.lsfo_maneuvering * maneuver_days
        + vessel.lsfo_port * port_days
        + vessel.lsfo_idle * idle_days
        + vessel.lsfo_ballast * ballast_days
        + vessel.lsfo_laden * laden_days
        + vessel.lsfo_idle * total_cong_days    # congestion = anchored/idle fuel
    )
    mgo_mt = (
        vessel.mgo_maneuvering * maneuver_days
        + vessel.mgo_port * port_days
        + vessel.mgo_idle * idle_days
        + vessel.mgo_ballast * ballast_days
        + vessel.mgo_laden * laden_days
        + vessel.mgo_idle * total_cong_days
    )
    lsfo_cost = lsfo_mt * lsfo_price
    mgo_cost = mgo_mt * mgo_price
    bunker_cost = lsfo_cost + mgo_cost

    # ── Other costs ──────────────────────────────────────────────────────────
    charter_hire = vessel.charter_hire_day * total_days
    stevedoring = (load_steve_per_mt + disch_steve_per_mt) * cargo_mt
    port_costs = load_port_nav + load_port_steve + disch_port_nav + disch_port_steve + stevedoring
    insurance = (vessel.insurance_annual / 365.0) * total_days
    other_costs = vessel.other_costs_per_voyage

    total_expenses = charter_hire + bunker_cost + port_costs + insurance + other_costs
    profit_loss = net_income - total_expenses

    # ── Two-phase breakdown ───────────────────────────────────────────────────
    # Phase 1 — Ballast: costs only for empty sailing leg to load port
    _bl_lsfo = (vessel.lsfo_ballast * ballast_days) * lsfo_price
    _bl_mgo  = (vessel.mgo_ballast  * ballast_days) * mgo_price
    _bl_hire = vessel.charter_hire_day * ballast_days
    _bl_total = _bl_hire + _bl_lsfo + _bl_mgo

    # Phase 2 — Laden: loaded leg + port time + cong (revenue + costs)
    _la_days = laden_days + port_days + idle_days + maneuver_days + total_cong_days
    _la_hire = vessel.charter_hire_day * _la_days

    ballast_phase = {
        'nm':           round(ballast_nm, 1),
        'days':         round(ballast_days, 2),
        'charter_cost': round(_bl_hire, 0),
        'bunker_cost':  round(_bl_lsfo + _bl_mgo, 0),
        'total_cost':   round(_bl_total, 0),
        'revenue':      0.0,
        'net':          round(-_bl_total, 0),
    }
    laden_phase = {
        'nm':            round(laden_nm, 1),
        'days':          round(_la_days, 2),
        'charter_cost':  round(_la_hire, 0),
        'bunker_cost':   round(lsfo_cost + mgo_cost - _bl_lsfo - _bl_mgo, 0),
        'port_cost':     round(port_costs, 0),
        'gross_freight': round(gross_freight, 0),
        'net_income':    round(net_income, 0),
        'net':           round(profit_loss, 0),
    }
    ballast_ratio = ballast_days / max(total_days, 1)

    return {
        'gross_freight': gross_freight,
        'brokerage': brokerage,
        'net_income': net_income,
        'charter_hire': charter_hire,
        'lsfo_mt': lsfo_mt,
        'mgo_mt': mgo_mt,
        'lsfo_cost': lsfo_cost,
        'mgo_cost': mgo_cost,
        'bunker_cost': bunker_cost,
        'port_costs': port_costs,
        'load_port_nav': load_port_nav,
        'load_port_steve': load_port_steve,
        'disch_port_nav': disch_port_nav,
        'disch_port_steve': disch_port_steve,
        'stevedoring': stevedoring,
        'insurance': insurance,
        'other_costs': other_costs,
        'total_expenses': total_expenses,
        'profit_loss': profit_loss,
        'maneuver_days': maneuver_days,
        'loading_days': loading_days,
        'discharge_days': discharge_days,
        'port_days': port_days,
        'idle_days': idle_days,
        'ballast_days': ballast_days,
        'laden_days': laden_days,
        'load_cong_days': load_cong_days,
        'disch_cong_days': disch_cong_days,
        'congestion_days': total_cong_days,
        'total_days': total_days,
        'profit_per_day': profit_loss / total_days,
        'profit_per_mt': profit_loss / cargo_mt if cargo_mt > 0 else 0.0,
        # Two-phase breakdown
        'ballast_phase':      ballast_phase,
        'laden_phase':        laden_phase,
        'ballast_ratio':      round(ballast_ratio, 3),
        'ballast_cost_total': round(_bl_total, 0),
    }


# ─── FAST LEG LIBRARY (NumPy vectorised) ─────────────────────────────────────

class FastLegLibrary:
    """
    Pre-computed NumPy arrays for all legs.
    Enables vectorised profit evaluation without Python loops.
    """

    def __init__(self, legs_df: pd.DataFrame, vessel: VesselConfig):
        self.vessel = vessel
        n = len(legs_df)

        self.origin_ids   = legs_df['origin_id'].values.astype(np.int32)
        self.dest_ids     = legs_df['dest_id'].values.astype(np.int32)
        self.laden_nm     = legs_df['distance_nm'].values.astype(np.float64)
        self.base_freight = legs_df['freight_rate_usd_mt'].values.astype(np.float64)
        self.load_rate    = legs_df['load_rate_mt_day'].values.astype(np.float64)
        self.disch_rate   = legs_df['disch_rate_mt_day'].values.astype(np.float64)
        self.load_nav     = legs_df['load_port_nav'].values.astype(np.float64)
        self.load_steve   = legs_df['load_port_steve'].values.astype(np.float64)
        self.disch_nav    = legs_df['disch_port_nav'].values.astype(np.float64)
        self.disch_steve  = legs_df['disch_port_steve'].values.astype(np.float64)

        # Congestion arrays (mean days per port call)
        if 'load_congestion_days' in legs_df.columns:
            self.load_cong_arr  = legs_df['load_congestion_days'].values.astype(np.float64)
            self.disch_cong_arr = legs_df['disch_congestion_days'].values.astype(np.float64)
        else:
            self.load_cong_arr  = np.full(n, 1.0)
            self.disch_cong_arr = np.full(n, 1.0)

        # Stevedoring rates (per MT) — applied only when FIO=False
        if 'load_steve_per_mt' in legs_df.columns:
            self.load_steve_per_mt_arr  = legs_df['load_steve_per_mt'].values.astype(np.float64)
            self.disch_steve_per_mt_arr = legs_df['disch_steve_per_mt'].values.astype(np.float64)
        else:
            self.load_steve_per_mt_arr  = np.zeros(n)
            self.disch_steve_per_mt_arr = np.zeros(n)

        self.origin_ports = legs_df['origin_port'].values
        self.dest_ports   = legs_df['dest_port'].values
        self.commodities  = legs_df['commodity'].values
        self.categories   = legs_df['category'].values

        # Fixed time components (no ballast, no volatility)
        cargo = vessel.dwcc
        self.loading_days_arr  = cargo / self.load_rate
        self.disch_days_arr    = cargo / self.disch_rate
        self.port_days_arr     = self.loading_days_arr + self.disch_days_arr
        self.idle_days_arr     = np.minimum(0.35 * self.port_days_arr, 1.5)
        self.laden_days_arr    = self.laden_nm / (vessel.speed_laden_knots * 24.0)
        self.port_costs_arr    = self.load_nav + self.load_steve + self.disch_nav + self.disch_steve

        # Pre-compute fixed portion of bunker (everything except ballast)
        m = MANEUVER_DAYS
        self._lsfo_fixed = (
            vessel.lsfo_maneuvering * m
            + vessel.lsfo_port * self.port_days_arr
            + vessel.lsfo_idle * self.idle_days_arr
            + vessel.lsfo_laden * self.laden_days_arr
        )
        self._mgo_fixed = (
            vessel.mgo_maneuvering * m
            + vessel.mgo_port * self.port_days_arr
            + vessel.mgo_idle * self.idle_days_arr
            + vessel.mgo_laden * self.laden_days_arr
        )
        self._days_fixed = (
            m
            + self.loading_days_arr
            + self.idle_days_arr
            + self.disch_days_arr
            + self.laden_days_arr
        )

        # Build per-origin index for fast lookup
        self.by_origin: Dict[int, np.ndarray] = {}
        for uid in np.unique(self.origin_ids):
            self.by_origin[int(uid)] = np.where(self.origin_ids == uid)[0]

        self.n_legs = n

    def evaluate_candidates(
        self,
        indices: np.ndarray,
        ballast_nm: np.ndarray,
        lsfo_price: float,
        mgo_price: float,
        freight_mult: np.ndarray,          # per-leg stochastic multiplier
        port_charge_mult: float = 1.0,     # stochastic ±15% on port nav charges
        cong_mult: float = 1.0,            # stochastic ±40% on congestion days
        use_stevedoring: bool = False,     # True = non-FIO terms
    ) -> np.ndarray:
        """
        Vectorised profit calculation for a set of candidate legs.
        Returns profit_per_day array (same length as indices).
        """
        v = self.vessel
        cargo = v.dwcc
        bd = ballast_nm / (v.speed_ballast_knots * 24.0)

        fr = self.base_freight[indices] * freight_mult
        gross = fr * cargo
        net   = gross * (1.0 - v.brokerage_pct - v.ad_com_pct)

        # Congestion days (stochastic variation)
        cong_days = np.maximum(
            (self.load_cong_arr[indices] + self.disch_cong_arr[indices]) * cong_mult, 0.0
        )

        lsfo  = self._lsfo_fixed[indices] + v.lsfo_ballast * bd + v.lsfo_idle * cong_days
        mgo   = self._mgo_fixed[indices]  + v.mgo_ballast * bd  + v.mgo_idle  * cong_days
        bunk  = lsfo * lsfo_price + mgo * mgo_price

        days  = self._days_fixed[indices] + bd + cong_days
        hire  = v.charter_hire_day * days
        ins   = (v.insurance_annual / 365.0) * days

        # Port nav costs with stochastic variation; stevedoring when non-FIO
        pc = (self.load_nav[indices] + self.disch_nav[indices]) * port_charge_mult
        pc += self.load_steve[indices] + self.disch_steve[indices]  # always include fixed steve
        if use_stevedoring:
            pc += (self.load_steve_per_mt_arr[indices] + self.disch_steve_per_mt_arr[indices]) * cargo

        other = v.other_costs_per_voyage

        profit = net - (hire + bunk + pc + ins + other)
        return profit / np.maximum(days, 0.01)

    def build_voyage_leg(
        self,
        idx: int,
        ballast_nm: float,
        ballast_from_port: str,
        lsfo_price: float,
        mgo_price: float,
        freight_rate: float,
        cong_mult: float = 1.0,
        port_charge_mult: float = 1.0,
        use_stevedoring: bool = False,
    ) -> VoyageLeg:
        """Build a full VoyageLeg from a leg index and runtime parameters."""
        v = self.vessel
        cargo = v.dwcc
        load_cong  = float(self.load_cong_arr[idx]) * cong_mult
        disch_cong = float(self.disch_cong_arr[idx]) * cong_mult
        # Add tidal waiting penalty for restricted ports
        if HAS_PORT_RESTRICTIONS:
            load_cong  += get_tidal_penalty(str(self.origin_ports[idx]))
            disch_cong += get_tidal_penalty(str(self.dest_ports[idx]))
        load_nav   = float(self.load_nav[idx]) * port_charge_mult
        disch_nav  = float(self.disch_nav[idx]) * port_charge_mult
        steve_load = float(self.load_steve_per_mt_arr[idx]) if use_stevedoring else 0.0
        steve_disch = float(self.disch_steve_per_mt_arr[idx]) if use_stevedoring else 0.0
        res = cost_voyage_exact(
            cargo_mt=cargo,
            freight_rate=freight_rate,
            laden_nm=float(self.laden_nm[idx]),
            ballast_nm=ballast_nm,
            load_rate_mt_day=float(self.load_rate[idx]),
            disch_rate_mt_day=float(self.disch_rate[idx]),
            load_port_nav=load_nav,
            load_port_steve=float(self.load_steve[idx]),
            disch_port_nav=disch_nav,
            disch_port_steve=float(self.disch_steve[idx]),
            vessel=v,
            lsfo_price=lsfo_price,
            mgo_price=mgo_price,
            load_cong_days=load_cong,
            disch_cong_days=disch_cong,
            load_steve_per_mt=steve_load,
            disch_steve_per_mt=steve_disch,
        )
        if res is None:
            return None

        leg = VoyageLeg(
            origin_id=int(self.origin_ids[idx]),
            dest_id=int(self.dest_ids[idx]),
            origin_port=str(self.origin_ports[idx]),
            dest_port=str(self.dest_ports[idx]),
            ballast_from_port=ballast_from_port,
            commodity=str(self.commodities[idx]),
            category=str(self.categories[idx]),
            cargo_mt=cargo,
            freight_rate=freight_rate,
            ballast_nm=ballast_nm,
            laden_nm=float(self.laden_nm[idx]),
            **{k: res[k] for k in res},
        )
        # Fill legacy aliases
        leg.revenue = res['gross_freight']
        leg.total_cost = res['total_expenses']
        leg.profit = res['profit_loss']
        leg.tce = (res['net_income'] - res['bunker_cost'] - res['port_costs']) / max(res['total_days'], 0.01)
        leg.distance_nm = float(self.laden_nm[idx])
        leg.ballast_distance_nm = ballast_nm
        leg.sailing_days_laden = res['laden_days']
        leg.sailing_days_ballast = res['ballast_days']
        leg.load_days = res['loading_days']
        leg.disch_days = res['discharge_days']
        leg.fuel_cost_laden = v.lsfo_laden * res['laden_days'] * lsfo_price
        leg.fuel_cost_ballast = v.lsfo_ballast * res['ballast_days'] * lsfo_price
        leg.load_port_charges = float(self.load_nav[idx]) + float(self.load_steve[idx])
        leg.disch_port_charges = float(self.disch_nav[idx]) + float(self.disch_steve[idx])
        leg.charter_hire_cost = res['charter_hire']
        return leg


# ─── NETWORK GRAPH ───────────────────────────────────────────────────────────

def build_voyage_graph(legs_df: pd.DataFrame, vessel: VesselConfig) -> Optional[object]:
    """Build a NetworkX directed weighted graph of voyage legs."""
    if not HAS_NX:
        return None

    G = nx.DiGraph()
    ports = set(legs_df['origin_port'].unique()) | set(legs_df['dest_port'].unique())
    G.add_nodes_from(ports)

    for _, row in legs_df.iterrows():
        res = cost_voyage_exact(
            cargo_mt=vessel.dwcc,
            freight_rate=row['freight_rate_usd_mt'],
            laden_nm=row['distance_nm'],
            ballast_nm=0.0,           # zero ballast for edge weight (no position dependency)
            load_rate_mt_day=row['load_rate_mt_day'],
            disch_rate_mt_day=row['disch_rate_mt_day'],
            load_port_nav=row.get('load_port_nav', row.get('load_port_charges', 10000)),
            load_port_steve=row.get('load_port_steve', 0),
            disch_port_nav=row.get('disch_port_nav', row.get('disch_port_charges', 20000)),
            disch_port_steve=row.get('disch_port_steve', 0),
            vessel=vessel,
        )
        if res is None:
            continue
        profit = res['profit_loss']
        days = res['total_days']
        # Use profit/day as weight; negate for "shortest path" algorithms
        G.add_edge(
            row['origin_port'], row['dest_port'],
            weight=-profit,          # negated for min-cost = max-profit
            profit=profit,
            profit_per_day=profit / max(days, 0.01),
            days=days,
            commodity=row['commodity'],
        )

    return G


def compute_port_centrality(G) -> Dict[str, float]:
    """Return normalised betweenness centrality for each port node."""
    if G is None or not HAS_NX:
        return {}
    try:
        centrality = nx.betweenness_centrality(G, weight='weight', normalized=True)
        return centrality
    except Exception:
        return {}


def find_communities(G) -> Dict[str, int]:
    """Return community label per port using greedy modularity."""
    if G is None or not HAS_NX:
        return {}
    try:
        ug = G.to_undirected()
        communities = nx.community.greedy_modularity_communities(ug)
        label_map = {}
        for i, comm in enumerate(communities):
            for node in comm:
                label_map[node] = i
        return label_map
    except Exception:
        return {}


def _sample_mult(rng, dist_type, vol,
                 tri_min=0.70, tri_mode=1.00, tri_max=1.40,
                 size=None, clip_lo=0.5, clip_hi=2.0):
    """Sample stochastic multiplier — Normal or Triangular."""
    if dist_type == 'triangular':
        if size is not None:
            return rng.triangular(tri_min, tri_mode, tri_max, size=size)
        return float(rng.triangular(tri_min, tri_mode, tri_max))
    else:
        if size is not None:
            return np.clip(1.0 + rng.normal(0.0, vol, size=size),
                           clip_lo, clip_hi)
        return float(np.clip(1.0 + rng.normal(0.0, vol), clip_lo, clip_hi))


# ─── GREEDY CONSTRUCTIVE HEURISTIC ───────────────────────────────────────────

def greedy_programme(
    fast_lib: FastLegLibrary,
    dist_matrix: np.ndarray,
    vessel: VesselConfig,
    rng: np.random.Generator,
    start_port_id: Optional[int] = None,
    lsfo_price: Optional[float] = None,
    mgo_price: Optional[float] = None,
    freight_vol: float = 0.15,
    temperature: float = 0.5,
    port_charge_vol: float = 0.15,
    congestion_vol: float = 0.40,
    use_stevedoring: bool = False,
    dist_type: str = 'normal',
    cong_min: float = 0.40,
    cong_mode: float = 1.00,
    cong_max: float = 2.00,
    freight_min: float = 0.70,
    freight_mode: float = 1.00,
    freight_max: float = 1.40,
    port_country_dict: Optional[dict] = None,
) -> VoyageProgramme:
    """
    Greedy construction: at each step pick the best-profit feasible leg
    from the current position using softmax selection.
    """
    if lsfo_price is None:
        lsfo_price = vessel.lsfo_price_mt
    if mgo_price is None:
        mgo_price = vessel.mgo_price_mt

    n_ports = dist_matrix.shape[0]
    if start_port_id is None:
        start_port_id = int(rng.integers(0, n_ports))

    programme = VoyageProgramme(algorithm='greedy')
    current_port_id = start_port_id
    current_port_name = _port_name_from_id(fast_lib, current_port_id)
    remaining_days = float(vessel.operating_days_year)
    elapsed_days = 0.0
    prev_commodity = ""

    # Iteration-level stochastic multipliers (fixed per programme)
    pc_mult = float(_sample_mult(
        rng, dist_type, port_charge_vol,
        tri_min=0.70, tri_mode=1.00, tri_max=1.40,
        clip_lo=0.5, clip_hi=2.0
    ))
    cong_mult = float(_sample_mult(
        rng, dist_type, congestion_vol,
        tri_min=cong_min, tri_mode=cong_mode, tri_max=cong_max,
        clip_lo=0.1, clip_hi=4.0
    ))

    for _ in range(60):  # max 60 voyages per year
        if remaining_days < 8.0:
            break

        # Collect all reachable leg indices
        cand_indices = []
        cand_ballast = []
        # Ports exempt from the laden-draft load-port check:
        # vessel loads partial cargo and leaves at reduced draft.
        _PARTIAL_LOAD_EXEMPT = {'Samarinda'}
        for orig_id, idx_arr in fast_lib.by_origin.items():
            b_nm = dist_matrix[current_port_id, orig_id]
            b_days = b_nm / (vessel.speed_ballast_knots * 24.0)
            if b_days > remaining_days * 0.45:
                continue
            # Block load ports where the vessel would depart laden above max_draft
            if HAS_PORT_RESTRICTIONS and len(idx_arr) > 0:
                orig = str(fast_lib.origin_ports[idx_arr[0]])
                if (orig not in _PARTIAL_LOAD_EXEMPT
                        and orig in RESTRICTED_PORTS
                        and vessel.draft_laden > RESTRICTED_PORTS[orig].get('max_draft', 99.0)):
                    continue
            # Quick total days estimate to filter out too-long voyages
            for i in idx_arr:
                est = fast_lib._days_fixed[i] + b_days
                if est <= remaining_days:
                    # Skip legs whose destination is physically blocked
                    if HAS_PORT_RESTRICTIONS:
                        dest = str(fast_lib.dest_ports[i])
                        if is_port_blocked(dest):
                            continue
                        # Explicit draft gate for known restricted discharge ports
                        if dest in DISCHARGE_BLOCKED_PORTS:
                            if vessel.draft_laden > DISCHARGE_BLOCKED_PORTS[dest]:
                                continue
                        # Block restricted ports where laden draft exceeds max_draft
                        # (vessel can still call ballast as origin/loading port)
                        if dest in RESTRICTED_PORTS:
                            _max_d = RESTRICTED_PORTS[dest].get('max_draft', 99.0)
                            if vessel.draft_laden > _max_d:
                                continue
                    cand_indices.append(i)
                    cand_ballast.append(b_nm)

        if not cand_indices:
            break

        cand_indices = np.array(cand_indices, dtype=np.int32)
        cand_ballast = np.array(cand_ballast, dtype=np.float64)

        # Subsample if too many candidates
        if len(cand_indices) > 300:
            sel = rng.choice(len(cand_indices), 300, replace=False)
            cand_indices = cand_indices[sel]
            cand_ballast = cand_ballast[sel]

        # Stochastic freight multipliers
        freight_mult = _sample_mult(
            rng, dist_type, freight_vol,
            tri_min=freight_min, tri_mode=freight_mode, tri_max=freight_max,
            size=len(cand_indices), clip_lo=0.5, clip_hi=2.0
        )

        ppd = fast_lib.evaluate_candidates(
            cand_indices, cand_ballast, lsfo_price, mgo_price, freight_mult,
            port_charge_mult=pc_mult, cong_mult=cong_mult,
            use_stevedoring=use_stevedoring,
        )

        # Apply backhaul penalty to scoring only (does not change final P&L)
        if HAS_CARGO_INTEL and port_country_dict:
            bh_penalties = np.array([
                get_backhaul_penalty(port_country_dict.get(str(fast_lib.dest_ports[i]), ""))
                for i in cand_indices
            ])
            ppd = ppd * bh_penalties

        # Softmax selection
        ppd_norm = ppd - ppd.max()
        exp_v = np.exp(ppd_norm / max(temperature, 0.01))
        exp_v = np.nan_to_num(exp_v, nan=0.0, posinf=1e10, neginf=0.0)
        s = exp_v.sum()
        probs = exp_v / s if s > 0 else np.ones(len(exp_v)) / len(exp_v)

        chosen = int(rng.choice(len(cand_indices), p=probs))
        idx = int(cand_indices[chosen])
        b_nm = float(cand_ballast[chosen])

        # Seasonal freight rate adjustment
        sim_month = int((elapsed_days / 30.0) % 12) + 1
        commodity_name = str(fast_lib.commodities[idx])
        seasonal_f = get_seasonal_factor(commodity_name, sim_month) if HAS_CARGO_INTEL else 1.0
        fr = float(fast_lib.base_freight[idx]) * float(freight_mult[chosen]) * seasonal_f

        leg = fast_lib.build_voyage_leg(
            idx, b_nm, current_port_name, lsfo_price, mgo_price, fr,
            cong_mult=cong_mult, port_charge_mult=pc_mult,
            use_stevedoring=use_stevedoring,
        )
        if leg is None or leg.total_days > remaining_days:
            continue

        # Hold cleaning: apply cost when switching commodity
        if HAS_CARGO_INTEL and prev_commodity:
            cleaning = get_cleaning_cost(prev_commodity, leg.commodity)
            if cleaning["cost"] > 0 or cleaning["days"] > 0:
                leg.other_costs       += cleaning["cost"]
                leg.total_expenses    += cleaning["cost"]
                leg.profit_loss       -= cleaning["cost"]
                leg.profit            -= cleaning["cost"]
                leg.total_days        += cleaning["days"]
                leg.charter_hire      += vessel.charter_hire_day * cleaning["days"]
                leg.total_expenses    += vessel.charter_hire_day * cleaning["days"]
                leg.profit_loss       -= vessel.charter_hire_day * cleaning["days"]
                leg.profit            -= vessel.charter_hire_day * cleaning["days"]
        leg.cleaning_cost  = get_cleaning_cost(prev_commodity, leg.commodity)["cost"] if HAS_CARGO_INTEL and prev_commodity else 0
        leg.cleaning_days  = get_cleaning_cost(prev_commodity, leg.commodity)["days"] if HAS_CARGO_INTEL and prev_commodity else 0.0
        leg.hold_switch    = f"{prev_commodity} -> {leg.commodity}" if prev_commodity and prev_commodity != leg.commodity else ""
        leg.seasonal_factor = seasonal_f
        leg.sim_month       = sim_month

        programme.legs.append(leg)
        programme.total_revenue += leg.gross_freight
        programme.total_cost += leg.total_expenses
        programme.total_profit += leg.profit_loss
        programme.total_days += leg.total_days
        programme.total_cargo_mt += leg.cargo_mt
        programme.n_voyages += 1
        programme.ports_visited.add(leg.origin_port)
        programme.ports_visited.add(leg.dest_port)
        programme.commodities_carried.add(leg.commodity)

        current_port_id = leg.dest_id
        current_port_name = leg.dest_port
        elapsed_days += leg.total_days
        remaining_days -= leg.total_days
        prev_commodity = leg.commodity

    _finalise_programme(programme, vessel)
    return programme


def _port_name_from_id(fast_lib: FastLegLibrary, port_id: int) -> str:
    mask = fast_lib.origin_ids == port_id
    if mask.any():
        return str(fast_lib.origin_ports[mask][0])
    mask2 = fast_lib.dest_ids == port_id
    if mask2.any():
        return str(fast_lib.dest_ports[mask2][0])
    return f'Port_{port_id}'


# ─── 2-OPT LOCAL SEARCH ──────────────────────────────────────────────────────

def two_opt_improve(
    programme: VoyageProgramme,
    dist_matrix: np.ndarray,
    vessel: VesselConfig,
    fast_lib: FastLegLibrary,
    lsfo_price: float,
    mgo_price: float,
    n_passes: int = 2,
) -> VoyageProgramme:
    """
    2-opt swap: try swapping the order of two voyage legs and keep if profit improves.
    After each swap, all downstream ballast distances cascade-recalculate.
    """
    legs = programme.legs[:]
    improved = True
    passes = 0

    while improved and passes < n_passes:
        improved = False
        passes += 1
        for i in range(len(legs)):
            for j in range(i + 1, len(legs)):
                # Swap legs[i] and legs[j]
                new_legs = legs[:]
                new_legs[i], new_legs[j] = new_legs[j], new_legs[i]
                new_legs = cascade_recalculate_legs(new_legs, i, dist_matrix, vessel, fast_lib, lsfo_price, mgo_price)
                new_profit = sum(l.profit_loss for l in new_legs)
                if new_profit > programme.total_profit + 1.0:
                    legs = new_legs
                    programme = _rebuild_programme(legs, vessel, programme.algorithm)
                    improved = True
                    break
            if improved:
                break

    if passes > 0:
        programme = _rebuild_programme(legs, vessel, programme.algorithm)
    return programme


def cascade_recalculate_legs(
    legs: List[VoyageLeg],
    from_idx: int,
    dist_matrix: np.ndarray,
    vessel: VesselConfig,
    fast_lib: FastLegLibrary,
    lsfo_price: float,
    mgo_price: float,
) -> List[VoyageLeg]:
    """
    Recalculate ballast distances and costs for legs[from_idx:] given
    that the vessel position at the start of from_idx may have changed.
    Also used for What-If cascade analysis in Tab 6.
    """
    for i in range(from_idx, len(legs)):
        leg = legs[i]
        if i == 0:
            # Starting position = leg's own origin (no prior voyage)
            new_ballast_nm = 0.0
            ballast_from = leg.origin_port
        else:
            prev = legs[i - 1]
            new_ballast_nm = float(dist_matrix[prev.dest_id, leg.origin_id])
            ballast_from = prev.dest_port

        fr = leg.freight_rate
        _lidx = _find_leg_idx(fast_lib, leg.origin_id, leg.dest_id, leg.commodity)
        res = cost_voyage_exact(
            cargo_mt=leg.cargo_mt,
            freight_rate=fr,
            laden_nm=leg.laden_nm,
            ballast_nm=new_ballast_nm,
            load_rate_mt_day=float(fast_lib.load_rate[_lidx]),
            disch_rate_mt_day=float(fast_lib.disch_rate[_lidx]),
            load_port_nav=leg.load_port_nav,
            load_port_steve=leg.load_port_steve,
            disch_port_nav=leg.disch_port_nav,
            disch_port_steve=leg.disch_port_steve,
            vessel=vessel,
            lsfo_price=lsfo_price,
            mgo_price=mgo_price,
            load_cong_days=leg.load_cong_days,
            disch_cong_days=leg.disch_cong_days,
        )
        if res is not None:
            for k, v in res.items():
                setattr(leg, k, v)
            leg.ballast_nm = new_ballast_nm
            leg.ballast_from_port = ballast_from
            leg.ballast_distance_nm = new_ballast_nm
            leg.ballast_days = res['ballast_days']
            leg.revenue = res['gross_freight']
            leg.total_cost = res['total_expenses']
            leg.profit = res['profit_loss']
            leg.charter_hire_cost = res['charter_hire']
        legs[i] = leg

    # Update cumulative fields
    cum_d, cum_p = 0.0, 0.0
    for leg in legs:
        cum_d += leg.total_days
        cum_p += leg.profit_loss
        leg.cum_days = cum_d
        leg.cum_profit = cum_p

    return legs


def _find_leg_idx(fast_lib: FastLegLibrary, origin_id: int, dest_id: int, commodity: str) -> int:
    """Find the index in fast_lib for a given origin/dest/commodity combination."""
    mask = (
        (fast_lib.origin_ids == origin_id)
        & (fast_lib.dest_ids == dest_id)
        & (fast_lib.commodities == commodity)
    )
    hits = np.where(mask)[0]
    return int(hits[0]) if len(hits) > 0 else 0


def _rebuild_programme(legs: List[VoyageLeg], vessel: VesselConfig, algorithm: str) -> VoyageProgramme:
    prog = VoyageProgramme(algorithm=algorithm)
    for leg in legs:
        prog.legs.append(leg)
        prog.total_revenue += leg.gross_freight
        prog.total_cost += leg.total_expenses
        prog.total_profit += leg.profit_loss
        prog.total_days += leg.total_days
        prog.total_cargo_mt += leg.cargo_mt
        prog.n_voyages += 1
        prog.ports_visited.add(leg.origin_port)
        prog.ports_visited.add(leg.dest_port)
        prog.commodities_carried.add(leg.commodity)
    _finalise_programme(prog, vessel)
    return prog


def _finalise_programme(programme: VoyageProgramme, vessel: VesselConfig):
    if programme.total_days > 0:
        programme.utilisation_pct = (programme.total_days / vessel.operating_days_year) * 100
        voyage_costs_ex_hire = programme.total_cost - sum(l.charter_hire for l in programme.legs)
        programme.avg_tce = (
            (programme.total_revenue - voyage_costs_ex_hire) / programme.total_days
        )
        programme.ebitda = programme.total_profit
    # Set cumulative fields
    cum_d, cum_p = 0.0, 0.0
    for leg in programme.legs:
        cum_d += leg.total_days
        cum_p += leg.profit_loss
        leg.cum_days = cum_d
        leg.cum_profit = cum_p


# ─── PROGRAMME → RESULT DICT ─────────────────────────────────────────────────

def programme_to_result(programme: VoyageProgramme, phase: int, iteration: int) -> dict:
    """Serialize a VoyageProgramme to a storable dict (full detail for Tab 5)."""
    legs = programme.legs
    total_ballast_days = sum(l.ballast_days for l in legs)
    total_laden_days   = sum(l.laden_days   for l in legs)
    ballast_ratio = total_ballast_days / max(total_ballast_days + total_laden_days, 1)
    ballast_cost_total = sum(l.ballast_cost_total for l in legs)
    return {
        'phase': phase,
        'iteration': iteration,
        'algorithm': programme.algorithm,
        'total_revenue': programme.total_revenue,
        'total_cost': programme.total_cost,
        'total_profit': programme.total_profit,
        'ebitda': programme.ebitda,
        'total_days': programme.total_days,
        'total_cargo_mt': programme.total_cargo_mt,
        'n_voyages': programme.n_voyages,
        'utilisation_pct': programme.utilisation_pct,
        'avg_tce': programme.avg_tce,
        'n_ports': len(programme.ports_visited),
        'ports_visited': list(programme.ports_visited),
        'commodities_carried': list(programme.commodities_carried),
        'legs': [_leg_to_dict(l) for l in legs],
        # Programme-level ballast stats
        'total_ballast_days': round(total_ballast_days, 1),
        'total_laden_days':   round(total_laden_days, 1),
        'ballast_ratio':      round(ballast_ratio, 3),
        'ballast_cost_total': round(ballast_cost_total, 0),
    }


def _leg_to_dict(l: VoyageLeg) -> dict:
    return {
        # Routing
        'origin_id': l.origin_id,
        'dest_id': l.dest_id,
        'origin_port': l.origin_port,
        'dest_port': l.dest_port,
        'ballast_from_port': l.ballast_from_port,
        # Cargo
        'commodity': l.commodity,
        'category': l.category,
        'cargo_mt': l.cargo_mt,
        'freight_rate': l.freight_rate,
        # Distances
        'ballast_nm': l.ballast_nm,
        'laden_nm': l.laden_nm,
        # Revenue
        'gross_freight': l.gross_freight,
        'brokerage': l.brokerage,
        'net_income': l.net_income,
        # Time
        'maneuver_days': l.maneuver_days,
        'loading_days': l.loading_days,
        'discharge_days': l.discharge_days,
        'port_days': l.port_days,
        'idle_days': l.idle_days,
        'ballast_days': l.ballast_days,
        'laden_days': l.laden_days,
        'total_days': l.total_days,
        # Bunkers
        'lsfo_mt': l.lsfo_mt,
        'mgo_mt': l.mgo_mt,
        'lsfo_cost': l.lsfo_cost,
        'mgo_cost': l.mgo_cost,
        'bunker_cost': l.bunker_cost,
        # Costs
        'charter_hire': l.charter_hire,
        'port_costs': l.port_costs,
        'load_port_nav': l.load_port_nav,
        'load_port_steve': l.load_port_steve,
        'disch_port_nav': l.disch_port_nav,
        'disch_port_steve': l.disch_port_steve,
        'stevedoring': l.stevedoring,
        'load_cong_days': l.load_cong_days,
        'disch_cong_days': l.disch_cong_days,
        'congestion_days': l.congestion_days,
        'insurance': l.insurance,
        'other_costs': l.other_costs,
        'total_expenses': l.total_expenses,
        # P&L
        'profit_loss': l.profit_loss,
        'profit_per_day': l.profit_per_day,
        'profit_per_mt': l.profit_per_mt,
        'cum_days': l.cum_days,
        'cum_profit': l.cum_profit,
        # Legacy aliases
        'revenue': l.gross_freight,
        'total_cost': l.total_expenses,
        'profit': l.profit_loss,
        'tce': l.tce,
        'distance_nm': l.laden_nm,
        'ballast_distance_nm': l.ballast_nm,
        # Two-phase breakdown
        'ballast_phase':      getattr(l, 'ballast_phase', {}),
        'laden_phase':        getattr(l, 'laden_phase', {}),
        'ballast_ratio':      getattr(l, 'ballast_ratio', 0.0),
        'ballast_cost_total': getattr(l, 'ballast_cost_total', 0.0),
        # Cargo intelligence
        'cleaning_cost':   getattr(l, 'cleaning_cost', 0),
        'cleaning_days':   getattr(l, 'cleaning_days', 0.0),
        'hold_switch':     getattr(l, 'hold_switch', ''),
        'seasonal_factor': getattr(l, 'seasonal_factor', 1.0),
        'sim_month':       getattr(l, 'sim_month', 1),
    }


# ─── MAIN SIMULATION ENTRY POINT ─────────────────────────────────────────────

def run_full_simulation(
    legs_df: pd.DataFrame,
    dist_matrix: np.ndarray,
    vessel: VesselConfig,
    sim_config: SimConfig,
    progress_callback=None,
    port_charge_vol: float = 0.15,
    congestion_vol: float = 0.40,
    use_stevedoring: bool = False,
) -> list:
    """
    Run the complete simulation using the chosen algorithm.
    Returns list of result dicts.
    """
    # Ensure legs_df has the new cost columns (backward compat with old data_processor)
    legs_df = _ensure_port_cost_columns(legs_df)

    # Build port → country lookup for backhaul penalty
    port_country_dict: dict = {}
    if 'dest_port' in legs_df.columns and 'dest_country' in legs_df.columns:
        for _, row in legs_df[['dest_port', 'dest_country']].drop_duplicates().iterrows():
            port_country_dict[str(row['dest_port'])] = str(row['dest_country'])
    if 'origin_port' in legs_df.columns and 'origin_country' in legs_df.columns:
        for _, row in legs_df[['origin_port', 'origin_country']].drop_duplicates().iterrows():
            port_country_dict.setdefault(str(row['origin_port']), str(row['origin_country']))

    fast_lib = FastLegLibrary(legs_df, vessel)
    all_results = []
    total = sim_config.n_iterations
    rng = np.random.default_rng(sim_config.random_seed)

    algo = sim_config.algorithm.lower()
    n_greedy = int(total * 0.30) if algo in ('hybrid', 'greedy') else 0
    n_mc = total - n_greedy

    # Split Monte Carlo into 3 phases
    n_explore  = int(n_mc * sim_config.exploration_pct)
    n_informed = int(n_mc * sim_config.informed_pct)
    n_exploit  = n_mc - n_explore - n_informed

    lsfo_base = vessel.lsfo_price_mt
    mgo_base  = vessel.mgo_price_mt

    # ── Greedy phase (first 30% for hybrid) ──────────────────────────────────
    if n_greedy > 0:
        if progress_callback:
            progress_callback("Greedy + Local Search", 0, total)

        n_ports = dist_matrix.shape[0]
        temperatures = np.linspace(1.5, 0.3, n_greedy)

        for i in range(n_greedy):
            lsfo, mgo = _stochastic_prices(
                rng, lsfo_base, mgo_base,
                sim_config.bunker_volatility,
                dist_type=sim_config.dist_type,
                b_min=sim_config.bunker_min,
                b_mode=sim_config.bunker_mode,
                b_max=sim_config.bunker_max,
            )

            start = int(rng.integers(0, n_ports))

            prog = greedy_programme(
                fast_lib, dist_matrix, vessel, rng,
                start_port_id=start,
                lsfo_price=lsfo, mgo_price=mgo,
                freight_vol=sim_config.freight_volatility,
                temperature=float(temperatures[i]),
                port_charge_vol=port_charge_vol,
                congestion_vol=congestion_vol,
                use_stevedoring=use_stevedoring,
                dist_type=sim_config.dist_type,
                cong_min=sim_config.cong_min,
                cong_mode=sim_config.cong_mode,
                cong_max=sim_config.cong_max,
                freight_min=sim_config.freight_min,
                freight_mode=sim_config.freight_mode,
                freight_max=sim_config.freight_max,
                port_country_dict=port_country_dict,
            )

            if sim_config.local_search_passes > 0 and prog.n_voyages > 2:
                prog = two_opt_improve(
                    prog, dist_matrix, vessel, fast_lib, lsfo, mgo,
                    n_passes=sim_config.local_search_passes,
                )

            all_results.append(programme_to_result(prog, phase=0, iteration=i))

            if progress_callback and i % max(1, n_greedy // 20) == 0:
                progress_callback("Greedy + Local Search", i, total)

    # ── Phase 1: Pure Exploration (Monte Carlo) ───────────────────────────────
    port_weights = None
    if progress_callback:
        progress_callback("Phase 1: Pure Exploration", n_greedy, total)

    for i in range(n_explore):
        lsfo, mgo = _stochastic_prices(
            rng, lsfo_base, mgo_base,
            sim_config.bunker_volatility,
            dist_type=sim_config.dist_type,
            b_min=sim_config.bunker_min,
            b_mode=sim_config.bunker_mode,
            b_max=sim_config.bunker_max,
        )
        prog = _mc_programme(fast_lib, dist_matrix, vessel, rng,
                             sim_config.temperature_explore, port_weights,
                             sim_config.freight_volatility, lsfo, mgo,
                             port_charge_vol=port_charge_vol,
                             congestion_vol=congestion_vol,
                             use_stevedoring=use_stevedoring,
                             dist_type=sim_config.dist_type,
                             cong_min=sim_config.cong_min,
                             cong_mode=sim_config.cong_mode,
                             cong_max=sim_config.cong_max,
                             freight_min=sim_config.freight_min,
                             freight_mode=sim_config.freight_mode,
                             freight_max=sim_config.freight_max,
                             port_country_dict=port_country_dict)
        all_results.append(programme_to_result(prog, phase=1, iteration=n_greedy + i))
        if progress_callback and i % max(1, n_explore // 20) == 0:
            progress_callback("Phase 1: Pure Exploration", n_greedy + i, total)

    # ── Compute port weights from Phase 1 ────────────────────────────────────
    port_weights = compute_port_weights(all_results)

    # ── Phase 2: Informed Exploration ────────────────────────────────────────
    if progress_callback:
        progress_callback("Phase 2: Informed Exploration", n_greedy + n_explore, total)

    for i in range(n_informed):
        lsfo, mgo = _stochastic_prices(
            rng, lsfo_base, mgo_base,
            sim_config.bunker_volatility,
            dist_type=sim_config.dist_type,
            b_min=sim_config.bunker_min,
            b_mode=sim_config.bunker_mode,
            b_max=sim_config.bunker_max,
        )
        prog = _mc_programme(fast_lib, dist_matrix, vessel, rng,
                             sim_config.temperature_informed, port_weights,
                             sim_config.freight_volatility, lsfo, mgo,
                             port_charge_vol=port_charge_vol,
                             congestion_vol=congestion_vol,
                             use_stevedoring=use_stevedoring,
                             dist_type=sim_config.dist_type,
                             cong_min=sim_config.cong_min,
                             cong_mode=sim_config.cong_mode,
                             cong_max=sim_config.cong_max,
                             freight_min=sim_config.freight_min,
                             freight_mode=sim_config.freight_mode,
                             freight_max=sim_config.freight_max,
                             port_country_dict=port_country_dict)
        all_results.append(programme_to_result(prog, phase=2, iteration=n_greedy + n_explore + i))
        if progress_callback and i % max(1, n_informed // 20) == 0:
            progress_callback("Phase 2: Informed Exploration", n_greedy + n_explore + i, total)

    # ── Update port weights ───────────────────────────────────────────────────
    port_weights = compute_port_weights(all_results, top_pct=0.05)

    # ── Phase 3: Exploitation ─────────────────────────────────────────────────
    if progress_callback:
        progress_callback("Phase 3: Intensive Exploitation", n_greedy + n_explore + n_informed, total)

    for i in range(n_exploit):
        lsfo, mgo = _stochastic_prices(
            rng, lsfo_base, mgo_base,
            sim_config.bunker_volatility,
            dist_type=sim_config.dist_type,
            b_min=sim_config.bunker_min,
            b_mode=sim_config.bunker_mode,
            b_max=sim_config.bunker_max,
        )
        prog = _mc_programme(fast_lib, dist_matrix, vessel, rng,
                             sim_config.temperature_exploit, port_weights,
                             sim_config.freight_volatility, lsfo, mgo,
                             port_charge_vol=port_charge_vol,
                             congestion_vol=congestion_vol,
                             use_stevedoring=use_stevedoring,
                             dist_type=sim_config.dist_type,
                             cong_min=sim_config.cong_min,
                             cong_mode=sim_config.cong_mode,
                             cong_max=sim_config.cong_max,
                             freight_min=sim_config.freight_min,
                             freight_mode=sim_config.freight_mode,
                             freight_max=sim_config.freight_max,
                             port_country_dict=port_country_dict)
        all_results.append(programme_to_result(prog, phase=3, iteration=n_greedy + n_explore + n_informed + i))
        if progress_callback and i % max(1, n_exploit // 20) == 0:
            progress_callback("Phase 3: Intensive Exploitation",
                              n_greedy + n_explore + n_informed + i, total)

    if progress_callback:
        progress_callback("Complete", total, total)

    return all_results


def _stochastic_prices(rng, lsfo_base, mgo_base, vol,
                       dist_type='normal',
                       b_min=0.75, b_mode=1.00, b_max=1.60):
    if dist_type == 'triangular':
        lsfo = lsfo_base * float(rng.triangular(b_min, b_mode, b_max))
        mgo  = mgo_base  * float(rng.triangular(b_min, b_mode, b_max))
    else:
        lsfo = lsfo_base * max(0.7, 1.0 + rng.normal(0, vol * 0.5))
        mgo  = mgo_base  * max(0.7, 1.0 + rng.normal(0, vol * 0.5))
    return lsfo, mgo


def _mc_programme(
    fast_lib, dist_matrix, vessel, rng, temperature, port_weights,
    freight_vol, lsfo_price, mgo_price,
    port_charge_vol: float = 0.15,
    congestion_vol: float = 0.40,
    use_stevedoring: bool = False,
    dist_type: str = 'normal',
    cong_min: float = 0.40,
    cong_mode: float = 1.00,
    cong_max: float = 2.00,
    freight_min: float = 0.70,
    freight_mode: float = 1.00,
    freight_max: float = 1.40,
    port_country_dict: Optional[dict] = None,
) -> VoyageProgramme:
    """Single Monte Carlo voyage programme using FastLegLibrary."""
    n_ports = dist_matrix.shape[0]
    programme = VoyageProgramme(algorithm='monte_carlo')

    if port_weights:
        pw_ids = [i for i in range(n_ports) if _port_name_from_id(fast_lib, i) in port_weights]
        if pw_ids:
            pw_vals = np.array([port_weights.get(_port_name_from_id(fast_lib, i), 0.5) for i in pw_ids])
            pw_vals /= pw_vals.sum()
            current_port_id = int(rng.choice(pw_ids, p=pw_vals))
        else:
            current_port_id = int(rng.integers(0, n_ports))
    else:
        current_port_id = int(rng.integers(0, n_ports))

    current_port_name = _port_name_from_id(fast_lib, current_port_id)
    remaining_days = float(vessel.operating_days_year)
    elapsed_days = 0.0
    prev_commodity = ""

    # Iteration-level stochastic multipliers (fixed per programme for consistency)
    pc_mult = float(_sample_mult(
        rng, dist_type, port_charge_vol,
        tri_min=0.70, tri_mode=1.00, tri_max=1.40,
        clip_lo=0.5, clip_hi=2.0
    ))
    cong_mult = float(_sample_mult(
        rng, dist_type, congestion_vol,
        tri_min=cong_min,
        tri_mode=cong_mode,
        tri_max=cong_max,
        clip_lo=0.1, clip_hi=4.0
    ))

    for _ in range(60):
        if remaining_days < 8.0:
            break

        cand_indices, cand_ballast = [], []
        _PARTIAL_LOAD_EXEMPT = {'Samarinda'}
        for orig_id, idx_arr in fast_lib.by_origin.items():
            b_nm = dist_matrix[current_port_id, orig_id]
            b_days = b_nm / (vessel.speed_ballast_knots * 24.0)
            if b_days > remaining_days * 0.45:
                continue
            # Block load ports where the vessel would depart laden above max_draft
            if HAS_PORT_RESTRICTIONS and len(idx_arr) > 0:
                orig = str(fast_lib.origin_ports[idx_arr[0]])
                if (orig not in _PARTIAL_LOAD_EXEMPT
                        and orig in RESTRICTED_PORTS
                        and vessel.draft_laden > RESTRICTED_PORTS[orig].get('max_draft', 99.0)):
                    continue
            for i in idx_arr:
                est = fast_lib._days_fixed[i] + b_days
                if est <= remaining_days:
                    # Skip blocked destinations and restricted ports that
                    # cannot receive a laden vessel (draft check)
                    if HAS_PORT_RESTRICTIONS:
                        dest = str(fast_lib.dest_ports[i])
                        if is_port_blocked(dest):
                            continue
                        # Explicit draft gate for known restricted discharge ports
                        if dest in DISCHARGE_BLOCKED_PORTS:
                            if vessel.draft_laden > DISCHARGE_BLOCKED_PORTS[dest]:
                                continue
                        if dest in RESTRICTED_PORTS:
                            _max_d = RESTRICTED_PORTS[dest].get('max_draft', 99.0)
                            if vessel.draft_laden > _max_d:
                                continue
                    cand_indices.append(i)
                    cand_ballast.append(b_nm)

        if not cand_indices:
            break

        cand_indices = np.array(cand_indices, dtype=np.int32)
        cand_ballast = np.array(cand_ballast, dtype=np.float64)

        if len(cand_indices) > 250:
            sel = rng.choice(len(cand_indices), 250, replace=False)
            cand_indices = cand_indices[sel]
            cand_ballast = cand_ballast[sel]

        freight_mult = _sample_mult(
            rng, dist_type, freight_vol,
            tri_min=freight_min, tri_mode=freight_mode, tri_max=freight_max,
            size=len(cand_indices), clip_lo=0.5, clip_hi=2.0
        )
        ppd = fast_lib.evaluate_candidates(
            cand_indices, cand_ballast, lsfo_price, mgo_price, freight_mult,
            port_charge_mult=pc_mult, cong_mult=cong_mult,
            use_stevedoring=use_stevedoring,
        )

        # Backhaul penalty applied to scoring only
        if HAS_CARGO_INTEL and port_country_dict:
            bh_penalties = np.array([
                get_backhaul_penalty(port_country_dict.get(str(fast_lib.dest_ports[i]), ""))
                for i in cand_indices
            ])
            ppd = ppd * bh_penalties

        ppd_norm = ppd - ppd.max()
        exp_v = np.exp(ppd_norm / max(temperature, 0.01))
        exp_v = np.nan_to_num(exp_v, nan=0.0, posinf=1e10, neginf=0.0)
        s = exp_v.sum()
        probs = exp_v / s if s > 0 else np.ones(len(exp_v)) / len(exp_v)

        chosen = int(rng.choice(len(cand_indices), p=probs))
        idx = int(cand_indices[chosen])
        b_nm = float(cand_ballast[chosen])

        # Seasonal freight rate adjustment
        sim_month = int((elapsed_days / 30.0) % 12) + 1
        commodity_name = str(fast_lib.commodities[idx])
        seasonal_f = get_seasonal_factor(commodity_name, sim_month) if HAS_CARGO_INTEL else 1.0
        fr = float(fast_lib.base_freight[idx]) * float(freight_mult[chosen]) * seasonal_f

        leg = fast_lib.build_voyage_leg(
            idx, b_nm, current_port_name, lsfo_price, mgo_price, fr,
            cong_mult=cong_mult, port_charge_mult=pc_mult,
            use_stevedoring=use_stevedoring,
        )
        if leg is None or leg.total_days > remaining_days:
            continue

        # Hold cleaning cost on commodity switch
        if HAS_CARGO_INTEL and prev_commodity:
            cleaning = get_cleaning_cost(prev_commodity, leg.commodity)
            if cleaning["cost"] > 0 or cleaning["days"] > 0:
                leg.other_costs    += cleaning["cost"]
                leg.total_expenses += cleaning["cost"]
                leg.profit_loss    -= cleaning["cost"]
                leg.profit         -= cleaning["cost"]
                leg.total_days     += cleaning["days"]
                extra_hire = vessel.charter_hire_day * cleaning["days"]
                leg.charter_hire   += extra_hire
                leg.total_expenses += extra_hire
                leg.profit_loss    -= extra_hire
                leg.profit         -= extra_hire
        leg.cleaning_cost   = get_cleaning_cost(prev_commodity, leg.commodity)["cost"] if HAS_CARGO_INTEL and prev_commodity else 0
        leg.cleaning_days   = get_cleaning_cost(prev_commodity, leg.commodity)["days"] if HAS_CARGO_INTEL and prev_commodity else 0.0
        leg.hold_switch     = f"{prev_commodity} -> {leg.commodity}" if prev_commodity and prev_commodity != leg.commodity else ""
        leg.seasonal_factor = seasonal_f
        leg.sim_month       = sim_month

        programme.legs.append(leg)
        programme.total_revenue += leg.gross_freight
        programme.total_cost += leg.total_expenses
        programme.total_profit += leg.profit_loss
        programme.total_days += leg.total_days
        programme.total_cargo_mt += leg.cargo_mt
        programme.n_voyages += 1
        programme.ports_visited.add(leg.origin_port)
        programme.ports_visited.add(leg.dest_port)
        programme.commodities_carried.add(leg.commodity)

        current_port_id = leg.dest_id
        current_port_name = leg.dest_port
        elapsed_days += leg.total_days
        remaining_days -= leg.total_days
        prev_commodity = leg.commodity

    _finalise_programme(programme, vessel)
    return programme


# ─── ANALYSIS ────────────────────────────────────────────────────────────────

def compute_port_weights(results, top_pct=0.10):
    if not results:
        return None
    profits = [r['total_profit'] for r in results]
    threshold = np.percentile(profits, (1 - top_pct) * 100)
    top_results = [r for r in results if r['total_profit'] >= threshold]
    port_counts = {}
    for r in top_results:
        for port in r['ports_visited']:
            port_counts[port] = port_counts.get(port, 0) + 1
    if not port_counts:
        return None
    max_count = max(port_counts.values())
    return {p: 0.5 + 1.5 * (c / max_count) for p, c in port_counts.items()}


def analyse_results(results, ports_df):
    """Comprehensive statistical analysis — backward-compatible with existing Tab 4."""
    df = pd.DataFrame([{k: v for k, v in r.items() if k != 'legs'} for r in results])
    analysis = {}

    import math as _math_stats

    _n       = len(df)
    _mean    = df['total_profit'].mean()
    _std     = df['total_profit'].std()
    _stderr  = _std / _math_stats.sqrt(_n) if _n > 1 else 0.0
    _loss_p  = (df['total_profit'] < 0).mean()   # proportion loss

    # z-values for confidence intervals
    _z95 = 1.959963985   # NORMSINV(0.975)
    _z90 = 1.644853627   # NORMSINV(0.95)

    analysis['summary'] = {
        'total_iterations': _n,
        # Central tendency
        'mean_profit':   _mean,
        'median_profit': df['total_profit'].median(),
        'std_profit':    _std,
        'stderr_profit': _stderr,
        # Percentiles
        'p5_profit':  df['total_profit'].quantile(0.05),  # VaR level
        'p10_profit': df['total_profit'].quantile(0.10),
        'p25_profit': df['total_profit'].quantile(0.25),
        'p75_profit': df['total_profit'].quantile(0.75),
        'p90_profit': df['total_profit'].quantile(0.90),
        'p95_profit': df['total_profit'].quantile(0.95),
        # Value at Risk — P5 (matches Excel PERCENTILE.INC at 0.05)
        'var_profit': df['total_profit'].quantile(0.05),
        # Confidence intervals on the mean
        'ci95_low':  _mean - _z95 * _stderr,
        'ci95_high': _mean + _z95 * _stderr,
        'ci90_low':  _mean - _z90 * _stderr,
        'ci90_high': _mean + _z90 * _stderr,
        # Risk metrics
        'loss_pct':       _loss_p * 100,        # % runs that lose money
        'profitable_pct': (1 - _loss_p) * 100,
        # Revenue/cost/operational
        'mean_revenue':    df['total_revenue'].mean(),
        'mean_cost':       df['total_cost'].mean(),
        'mean_tce':        df['avg_tce'].mean(),
        'median_tce':      df['avg_tce'].median(),
        'mean_voyages':    df['n_voyages'].mean(),
        'mean_utilisation':df['utilisation_pct'].mean(),
        'mean_cargo':      df['total_cargo_mt'].mean(),
        'mean_ports':      df['n_ports'].mean(),
    }

    top_10_pct = df.nlargest(max(1, len(df) // 10), 'total_profit')
    top_results = [results[i] for i in top_10_pct.index]

    port_freq, port_revenue = {}, {}
    for r in top_results:
        for leg in r['legs']:
            for port in [leg['origin_port'], leg['dest_port']]:
                port_freq[port] = port_freq.get(port, 0) + 1
                port_revenue[port] = port_revenue.get(port, 0) + leg.get('gross_freight', leg.get('revenue', 0))
    analysis['port_ranking'] = [
        {'port': p, 'frequency': f, 'frequency_pct': f / len(top_results) * 100,
         'avg_revenue_contribution': port_revenue.get(p, 0) / max(1, f)}
        for p, f in sorted(port_freq.items(), key=lambda x: -x[1])
    ]

    comm_freq, comm_revenue, comm_profit = {}, {}, {}
    for r in top_results:
        for leg in r['legs']:
            c = leg['commodity']
            comm_freq[c] = comm_freq.get(c, 0) + 1
            comm_revenue[c] = comm_revenue.get(c, 0) + leg.get('gross_freight', leg.get('revenue', 0))
            comm_profit[c] = comm_profit.get(c, 0) + leg.get('profit_loss', leg.get('profit', 0))
    analysis['commodity_ranking'] = [
        {'commodity': c, 'frequency': f,
         'total_revenue': comm_revenue.get(c, 0),
         'total_profit': comm_profit.get(c, 0),
         'avg_profit_per_leg': comm_profit.get(c, 0) / max(1, f)}
        for c, f in sorted(comm_freq.items(), key=lambda x: -x[1])
    ]

    route_freq, route_profit = {}, {}
    for r in top_results:
        for leg in r['legs']:
            route = f"{leg['origin_port']} → {leg['dest_port']}"
            route_freq[route] = route_freq.get(route, 0) + 1
            route_profit[route] = route_profit.get(route, 0) + leg.get('profit_loss', leg.get('profit', 0))
    analysis['route_ranking'] = [
        {'route': route, 'frequency': f,
         'total_profit': route_profit.get(route, 0),
         'avg_profit': route_profit.get(route, 0) / max(1, f)}
        for route, f in sorted(route_freq.items(), key=lambda x: -x[1])[:50]
    ]

    network_groups = df.groupby('n_ports').agg({
        'total_profit': ['mean', 'median', 'std', 'count'],
        'avg_tce': 'mean',
        'utilisation_pct': 'mean',
    }).reset_index()
    network_groups.columns = ['n_ports', 'mean_profit', 'median_profit', 'std_profit',
                               'count', 'mean_tce', 'mean_utilisation']
    analysis['network_size'] = network_groups.to_dict('records')

    top_20 = df.nlargest(20, 'total_profit')
    top_programmes = []
    for idx in top_20.index:
        r = results[idx]
        top_programmes.append({
            'rank': len(top_programmes) + 1,
            'total_revenue': r['total_revenue'],
            'total_cost': r['total_cost'],
            'total_profit': r['total_profit'],
            'ebitda': r.get('ebitda', r['total_profit']),
            'avg_tce': r['avg_tce'],
            'n_voyages': r['n_voyages'],
            'utilisation_pct': r['utilisation_pct'],
            'total_cargo_mt': r['total_cargo_mt'],
            'n_ports': r['n_ports'],
            'ports': r['ports_visited'],
            'commodities': r['commodities_carried'],
            'algorithm': r.get('algorithm', 'monte_carlo'),
            'legs': r['legs'],
            'ballast_ratio':      r.get('ballast_ratio', 0.0),
            'ballast_cost_total': r.get('ballast_cost_total', 0.0),
            'total_ballast_days': r.get('total_ballast_days', 0.0),
            'total_laden_days':   r.get('total_laden_days', 0.0),
        })
    analysis['top_programmes'] = top_programmes

    phase_stats = df.groupby('phase').agg({
        'total_profit': ['mean', 'median', 'max'],
        'avg_tce': 'mean',
    }).reset_index()
    phase_stats.columns = ['phase', 'mean_profit', 'median_profit', 'max_profit', 'mean_tce']
    analysis['phase_comparison'] = phase_stats.to_dict('records')

    return analysis


def _ensure_port_cost_columns(legs_df: pd.DataFrame) -> pd.DataFrame:
    """Add V2 port cost columns if only V1 columns present (backward compat)."""
    df = legs_df.copy()
    if 'load_port_nav' not in df.columns:
        df['load_port_nav'] = df.get('load_port_charges', 10000)
    if 'load_port_steve' not in df.columns:
        df['load_port_steve'] = 0.0
    if 'disch_port_nav' not in df.columns:
        df['disch_port_nav'] = df.get('disch_port_charges', 20000)
    if 'disch_port_steve' not in df.columns:
        df['disch_port_steve'] = 0.0
    if 'load_congestion_days' not in df.columns:
        df['load_congestion_days'] = 1.0
    if 'disch_congestion_days' not in df.columns:
        df['disch_congestion_days'] = 1.0
    if 'load_steve_per_mt' not in df.columns:
        df['load_steve_per_mt'] = 0.0
    if 'disch_steve_per_mt' not in df.columns:
        df['disch_steve_per_mt'] = 0.0
    return df
