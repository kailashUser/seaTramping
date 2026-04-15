"""
Simulation diagnostic log writer for COMPASS.
Called from app.py after every simulation run.
Output: simulation_log.txt in the Simulation/ root folder.
"""
import os
from datetime import datetime


# ── Helpers ───────────────────────────────────────────────────────────────────

def _d(v, fmt=","):
    """Format a number with commas, or return 'N/A'."""
    if v is None:
        return "N/A"
    try:
        return f"{v:{fmt}}"
    except Exception:
        return str(v)


def _usd(v):
    """Format as $X,XXX or ($X,XXX) for negatives."""
    if v is None:
        return "N/A"
    try:
        if v < 0:
            return f"(${abs(v):,.0f})"
        return f"${v:,.0f}"
    except Exception:
        return str(v)


def _pct(v):
    if v is None:
        return "N/A"
    return f"{v:.1f}%"


def _line(char="─", width=65):
    return char * width


# ── Main log builder ──────────────────────────────────────────────────────────

def build_simulation_log(
    elapsed: float,
    sim_config,          # SimConfig dataclass
    vessel,              # VesselConfig dataclass
    algo_display: str,   # human-readable algorithm name
    legs_df,             # final filtered legs DataFrame
    analysis: dict,      # from analyse_results()
    filter_stats: dict,  # from data_processor._FILTER_STATS
    warnings: list = None,
) -> str:
    """
    Build and return the full simulation log as a string.
    """
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = []
    W = 65  # line width

    def hdr(title):
        lines.append("")
        lines.append(f"── {title} " + "─" * max(0, W - len(title) - 4))

    def row(label, value, indent=0):
        pad = " " * indent
        lines.append(f"{pad}{label}: {value}")

    # ── SIMULATION RUN LOG ────────────────────────────────────────────────────
    lines.append(_line("─", W + 2))
    lines.append("  COMPASS SIMULATION RUN LOG")
    lines.append(_line("─", W + 2))

    hdr("SIMULATION RUN LOG")
    row("Timestamp",  ts)
    row("Iterations", f"{sim_config.n_iterations:,}")
    row("Algorithm",  algo_display)
    seed_str = str(sim_config.random_seed) if sim_config.random_seed is not None else "None (random)"
    row("Random seed", seed_str)
    row("Duration",   f"{elapsed:.1f} seconds")

    # ── VESSEL CONFIG ─────────────────────────────────────────────────────────
    hdr("VESSEL CONFIG")
    row("DWT",          f"{vessel.dwt:,.0f} MT")
    row("DWCC",         f"{vessel.dwcc:,.0f} MT")
    row("Draft laden",  f"{vessel.draft_laden:.1f}m | Draft ballast: {vessel.draft_ballast:.1f}m")
    row("LOA",          f"{vessel.loa:.0f}m | Beam: {vessel.beam:.0f}m")
    row("Speed laden",  f"{vessel.speed_laden_knots:.1f} kn | Speed ballast: {vessel.speed_ballast_knots:.1f} kn")
    row("Charter hire", f"${vessel.charter_hire_day:,.0f}/day")
    row("LSFO",         f"${vessel.lsfo_price_mt:,.0f}/MT | MGO: ${vessel.mgo_price_mt:,.0f}/MT")

    # ── PORT VALIDATION SUMMARY ───────────────────────────────────────────────
    hdr("PORT VALIDATION SUMMARY")

    _n_ports_matrix = filter_stats.get('n_ports', 'N/A')
    _n_active       = len(filter_stats.get('active_ports', []))

    try:
        from data.port_restrictions import NOT_SUITABLE_PORTS, RESTRICTED_PORTS
        blocked_names   = ", ".join(sorted(NOT_SUITABLE_PORTS)) if NOT_SUITABLE_PORTS else "None"
        restricted_names = ", ".join(sorted(RESTRICTED_PORTS.keys())) if RESTRICTED_PORTS else "None"
    except ImportError:
        blocked_names    = "N/A (port_restrictions.py not found)"
        restricted_names = "N/A"

    row("Total ports in D1 matrix",      str(_n_ports_matrix))
    row("Active ports in simulation",    str(_n_active))
    row("Ports blocked (NOT_SUITABLE)",  blocked_names)
    row("Ports restricted",              restricted_names)

    # ── DATA FILTER SUMMARY ───────────────────────────────────────────────────
    hdr("DATA FILTER SUMMARY")

    n_raw        = filter_stats.get('n_raw', 'N/A')
    n_intra      = filter_stats.get('n_intra_sea', 'N/A')
    n_no_bb      = filter_stats.get('n_no_bb', 'N/A')
    n_no_blocked = filter_stats.get('n_no_blocked', 'N/A')
    n_final      = filter_stats.get('n_final', 'N/A')
    cat_counts   = filter_stats.get('categories', {})

    row("Total routes in D1 matrix",    f"{n_raw:,}" if isinstance(n_raw, int) else str(n_raw))
    if isinstance(n_intra, int) and isinstance(n_raw, int) and n_intra < n_raw:
        _intra_label = f"{n_intra:,} ({n_raw - n_intra:,} non-SEA routes removed)"
    else:
        _intra_label = f"{n_intra:,} (all routes confirmed SEA region)" if isinstance(n_intra, int) else str(n_intra)
    row("After Intra-SEA filter",       _intra_label)
    row("After Break-Bulk filter",      f"{n_no_bb:,}" if isinstance(n_no_bb, int) else str(n_no_bb))
    row("After port validation filter", f"{n_no_blocked:,}" if isinstance(n_no_blocked, int) else str(n_no_blocked))
    row("Final routes used",            f"{n_final:,}" if isinstance(n_final, int) else str(n_final))

    if cat_counts and isinstance(n_final, int) and n_final > 0:
        cat_parts = []
        for cat, cnt in sorted(cat_counts.items(), key=lambda x: -x[1]):
            pct = cnt / n_final * 100
            cat_parts.append(f"{cat} ({cnt:,} = {pct:.1f}%)")
        row("Categories", ", ".join(cat_parts))

    # ── SIMULATION RESULTS ────────────────────────────────────────────────────
    hdr("SIMULATION RESULTS")

    s = analysis.get('summary', {})
    top_progs = analysis.get('top_programmes', [])

    best_profit = top_progs[0]['total_profit'] if top_progs else None
    mean_ballast_pct = None
    if top_progs:
        brs = [p.get('ballast_ratio', 0.0) for p in top_progs if p.get('ballast_ratio') is not None]
        if brs:
            mean_ballast_pct = sum(brs) / len(brs) * 100

    row("Best programme profit",   _usd(best_profit))
    row("Mean profit (all iters)", _usd(s.get('mean_profit')))
    row("P10 (worst 10%)",         _usd(s.get('p10_profit')))
    row("P90 (best 10%)",          _usd(s.get('p90_profit')))
    row("% Profitable programmes", _pct(s.get('profitable_pct')))
    row("Mean TCE",                f"${s.get('mean_tce', 0):,.0f}/day" if s.get('mean_tce') is not None else "N/A")
    if mean_ballast_pct is not None:
        row("Mean ballast ratio (top progs)", f"{mean_ballast_pct:.1f}%")

    # ── TOP PROGRAMME #1 ──────────────────────────────────────────────────────
    if top_progs:
        p1 = top_progs[0]
        hdr("TOP PROGRAMME #1")
        row("Total profit",   _usd(p1['total_profit']))
        row("Voyages",        str(p1['n_voyages']))
        row("TCE",            f"${p1['avg_tce']:,.0f}/day")
        br = p1.get('ballast_ratio')
        if br is not None:
            row("Ballast ratio", f"{br * 100:.1f}%")
        row("Algorithm",      p1.get('algorithm', 'monte_carlo'))
        lines.append("")

        for vi, leg in enumerate(p1.get('legs', []), 1):
            origin    = leg.get('origin_port', '?')
            dest      = leg.get('dest_port', '?')
            commodity = leg.get('commodity', '?')
            cargo_mt  = leg.get('cargo_mt', 0)
            laden_nm  = leg.get('laden_nm', 0)
            laden_d   = leg.get('laden_days', 0)
            fr        = leg.get('freight_rate', 0)
            rev       = leg.get('gross_freight', 0)
            ball_nm   = leg.get('ballast_nm', 0)
            ball_d    = leg.get('ballast_days', 0)
            pl        = leg.get('profit_loss', leg.get('profit', 0))
            hire      = leg.get('charter_hire', 0)
            bunker    = leg.get('bunker_cost', 0)
            _bp = leg.get('ballast_phase')
            if isinstance(_bp, dict):
                ball_cost = _bp.get('total_cost', _bp.get('cost', 0))
            else:
                ball_cost = (
                    vessel.charter_hire_day * ball_d
                    + vessel.lsfo_ballast * ball_d * vessel.lsfo_price_mt
                )

            lines.append(f"  Voyage {vi}: {origin} → {dest} | {commodity} | {cargo_mt:,.0f} MT")
            lines.append(f"    Laden:   {laden_nm:,.0f} NM | {laden_d:.1f} days | "
                         f"Freight: ${fr:.2f}/MT | Revenue: {_usd(rev)}")
            lines.append(f"    Ballast: {ball_nm:,.0f} NM | {ball_d:.1f} days | "
                         f"Ballast cost: {_usd(ball_cost)}")
            lines.append(f"    P&L: {_usd(pl)} | Charter hire: {_usd(hire)} | Bunker: {_usd(bunker)}")

            # Hold cleaning if present
            cleaning_cost = leg.get('cleaning_cost', 0)
            hold_switch   = leg.get('hold_switch', '')
            if cleaning_cost and cleaning_cost > 0 and hold_switch:
                lines.append(f"    Hold cleaning: {hold_switch} → ${cleaning_cost:,.0f}")
            lines.append("")

    # ── CARGO MIX ─────────────────────────────────────────────────────────────
    hdr("CARGO MIX (top programme #1)")

    if top_progs:
        comm_counts: dict = {}
        for leg in top_progs[0].get('legs', []):
            c = leg.get('commodity', 'Unknown')
            comm_counts[c] = comm_counts.get(c, 0) + 1
        total_legs = sum(comm_counts.values())
        for comm, cnt in sorted(comm_counts.items(), key=lambda x: -x[1]):
            pct = cnt / total_legs * 100 if total_legs else 0
            lines.append(f"  {comm:<28} {cnt:>3} voyages ({pct:.1f}%)")

    # ── DISTANCE MATRIX ───────────────────────────────────────────────────────
    hdr("DISTANCE MATRIX")

    try:
        from data.sea_distances_loader import _DISTANCE_MATRIX, is_loaded
        if is_loaded():
            n_ports_mat  = len(_DISTANCE_MATRIX)
            n_routes_mat = sum(len(v) for v in _DISTANCE_MATRIX.values())
            # Estimate coverage: count non-zero non-self legs in final legs_df
            if hasattr(legs_df, '__len__') and len(legs_df) > 0:
                lines.append("  Source: Searoute EU maritime routing network (real sea distances)")
                lines.append(f"  Matrix: {n_ports_mat} ports × {n_ports_mat} ports = {n_routes_mat:,} routes")
            else:
                lines.append("  Source: Searoute EU maritime routing network")
        else:
            lines.append("  Source: Haversine × correction factor (searoute matrix not loaded)")
    except ImportError:
        lines.append("  Source: Haversine × correction factor")

    # ── ERRORS / WARNINGS ─────────────────────────────────────────────────────
    hdr("ERRORS / WARNINGS")

    if warnings:
        for w in warnings:
            lines.append(f"  WARNING: {w}")
    else:
        lines.append("  No errors or warnings recorded.")

    # Footer
    lines.append("")
    lines.append(_line("─", W + 2))
    lines.append(f"  Log generated: {ts}")
    lines.append(_line("─", W + 2))
    lines.append("")

    return "\n".join(lines)


def write_simulation_log(log_text: str, log_path: str) -> str:
    """Write log_text to log_path. Returns the path written."""
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(log_text)
    return log_path
