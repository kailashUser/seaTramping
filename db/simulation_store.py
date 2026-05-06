"""
simulation_store.py
SQLite persistence for COMPASS SEA Tramping simulation runs.

Tables
------
simulation_runs      — 1 row per run (vessel config + summary stats)
iteration_results    — 1 row per Monte Carlo iteration (all N iterations, scalars only)
top_programme_legs   — full voyage-leg detail for the top-50 programmes per run

Design decisions
----------------
* All inserts use executemany() inside a single transaction — no per-row overhead.
* Legs are stored only for top-50 programmes; all N iteration scalars are stored in full.
* init_db() is idempotent (CREATE TABLE IF NOT EXISTS) — safe to call on every app start.
* Every public function wraps DB access in try/except so a DB failure never crashes the app.
"""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


# ── Schema ────────────────────────────────────────────────────────────────────

_DDL = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous  = NORMAL;

CREATE TABLE IF NOT EXISTS simulation_runs (
    run_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at           TEXT    NOT NULL,
    vessel_name      TEXT    DEFAULT '',
    vessel_imo       TEXT    DEFAULT '',
    dwt              REAL,
    dwcc             REAL,
    speed_laden      REAL,
    speed_ballast    REAL,
    charter_hire     REAL,
    lsfo_price       REAL,
    mgo_price        REAL,
    n_iterations     INTEGER,
    algorithm        TEXT,
    freight_vol      REAL,
    bunker_vol       REAL,
    elapsed_sec      REAL,
    mean_profit      REAL,
    median_profit    REAL,
    std_profit       REAL,
    p10_profit       REAL,
    p90_profit       REAL,
    var_profit       REAL,
    median_tce       REAL,
    mean_tce         REAL,
    profitable_pct   REAL,
    total_iterations INTEGER
);

CREATE TABLE IF NOT EXISTS iteration_results (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id           INTEGER NOT NULL REFERENCES simulation_runs(run_id),
    iteration        INTEGER NOT NULL,
    total_profit     REAL,
    total_revenue    REAL,
    total_cost       REAL,
    avg_tce          REAL,
    n_voyages        INTEGER,
    n_ports          INTEGER,
    utilisation_pct  REAL,
    total_cargo_mt   REAL,
    ballast_ratio    REAL,
    algorithm        TEXT,
    phase            TEXT
);

CREATE TABLE IF NOT EXISTS top_programme_legs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id           INTEGER NOT NULL REFERENCES simulation_runs(run_id),
    programme_rank   INTEGER NOT NULL,
    voyage_num       INTEGER NOT NULL,
    origin_port      TEXT,
    dest_port        TEXT,
    commodity        TEXT,
    freight_rate     REAL,
    cargo_mt         REAL,
    gross_freight    REAL,
    profit_loss      REAL,
    laden_nm         REAL,
    ballast_nm       REAL,
    laden_days       REAL,
    ballast_days     REAL,
    total_days       REAL,
    bunker_cost      REAL,
    port_costs       REAL
);

CREATE INDEX IF NOT EXISTS idx_iter_run  ON iteration_results(run_id);
CREATE INDEX IF NOT EXISTS idx_iter_prof ON iteration_results(run_id, total_profit);
CREATE INDEX IF NOT EXISTS idx_legs_run  ON top_programme_legs(run_id, programme_rank);
"""


# ── Public API ────────────────────────────────────────────────────────────────

def init_db(db_file: str) -> None:
    """Create tables and indexes. Safe to call on every Streamlit app start."""
    Path(db_file).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_file)
    try:
        con.executescript(_DDL)
        con.commit()
    finally:
        con.close()


def save_run(
    db_file: str,
    results: list,
    analysis: dict,
    vessel,
    sim_config,
    elapsed_sec: float,
    vessel_name: str = "",
    vessel_imo: str = "",
    top_n: int = 50,
) -> int:
    """
    Persist a completed simulation run in a single transaction.

    Parameters
    ----------
    results      : raw list returned by run_full_simulation()
    analysis     : dict returned by analyse_results()
    vessel       : VesselConfig instance
    sim_config   : SimConfig instance
    elapsed_sec  : wall-clock time of the simulation run
    vessel_name  : display name (from session_state, may be empty)
    vessel_imo   : IMO number string (may be empty)
    top_n        : how many top programmes to store full leg detail for

    Returns
    -------
    run_id : int — the newly created run_id
    """
    s      = analysis["summary"]
    run_at = datetime.now(timezone.utc).isoformat()

    con = sqlite3.connect(db_file)
    try:
        cur = con.cursor()

        # ── 1. Run header ──────────────────────────────────────────────────
        cur.execute(
            """
            INSERT INTO simulation_runs (
                run_at, vessel_name, vessel_imo, dwt, dwcc,
                speed_laden, speed_ballast, charter_hire, lsfo_price, mgo_price,
                n_iterations, algorithm, freight_vol, bunker_vol, elapsed_sec,
                mean_profit, median_profit, std_profit,
                p10_profit, p90_profit, var_profit,
                median_tce, mean_tce, profitable_pct, total_iterations
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                run_at, vessel_name or "", vessel_imo or "",
                float(vessel.dwt),   float(vessel.dwcc),
                float(vessel.speed_laden_knots), float(vessel.speed_ballast_knots),
                float(vessel.charter_hire_day),
                float(vessel.lsfo_price_mt),     float(vessel.mgo_price_mt),
                int(sim_config.n_iterations),    str(sim_config.algorithm),
                float(sim_config.freight_volatility), float(sim_config.bunker_volatility),
                float(elapsed_sec),
                float(s["mean_profit"]),   float(s["median_profit"]),
                float(s["std_profit"]),
                float(s["p10_profit"]),    float(s["p90_profit"]),
                float(s["var_profit"]),
                float(s["median_tce"]),    float(s["mean_tce"]),
                float(s["profitable_pct"]),
                int(s["total_iterations"]),
            ),
        )
        run_id = cur.lastrowid

        # ── 2. All iteration scalars (bulk) ────────────────────────────────
        iter_rows = [
            (
                run_id, i,
                float(r.get("total_profit", 0)),
                float(r.get("total_revenue", 0)),
                float(r.get("total_cost", 0)),
                float(r.get("avg_tce", 0)),
                int(r.get("n_voyages", 0)),
                int(r.get("n_ports", 0)),
                float(r.get("utilisation_pct", 0)),
                float(r.get("total_cargo_mt", 0)),
                float(r.get("ballast_ratio", 0)),
                str(r.get("algorithm", "")),
                str(r.get("phase", "")),
            )
            for i, r in enumerate(results)
        ]
        cur.executemany(
            """
            INSERT INTO iteration_results (
                run_id, iteration, total_profit, total_revenue, total_cost,
                avg_tce, n_voyages, n_ports, utilisation_pct, total_cargo_mt,
                ballast_ratio, algorithm, phase
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            iter_rows,
        )

        # ── 3. Top-N programme legs (bulk) ─────────────────────────────────
        top_progs = analysis.get("top_programmes", [])[:top_n]
        leg_rows = []
        for prog in top_progs:
            rank = prog["rank"]
            for vi, leg in enumerate(prog.get("legs", []), 1):
                leg_rows.append((
                    run_id, rank, vi,
                    leg.get("origin_port", ""),
                    leg.get("dest_port", ""),
                    leg.get("commodity", ""),
                    float(leg.get("freight_rate", 0)),
                    float(leg.get("cargo_mt", 0)),
                    float(leg.get("gross_freight", leg.get("revenue", 0))),
                    float(leg.get("profit_loss", leg.get("profit", 0))),
                    float(leg.get("laden_nm", leg.get("distance_nm", 0))),
                    float(leg.get("ballast_nm", leg.get("ballast_distance_nm", 0))),
                    float(leg.get("laden_days", 0)),
                    float(leg.get("ballast_days", 0)),
                    float(leg.get("total_days", 0)),
                    float(leg.get("bunker_cost", 0)),
                    float(leg.get("port_costs", 0)),
                ))
        if leg_rows:
            cur.executemany(
                """
                INSERT INTO top_programme_legs (
                    run_id, programme_rank, voyage_num,
                    origin_port, dest_port, commodity,
                    freight_rate, cargo_mt, gross_freight, profit_loss,
                    laden_nm, ballast_nm, laden_days, ballast_days, total_days,
                    bunker_cost, port_costs
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                leg_rows,
            )

        con.commit()
        return run_id

    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def get_run_history(db_file: str, limit: int = 20) -> list:
    """Return the last `limit` runs as a list of dicts, newest first."""
    try:
        con = sqlite3.connect(db_file)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute(
            """
            SELECT run_id, run_at, vessel_name, vessel_imo,
                   dwt, dwcc, charter_hire, n_iterations, algorithm,
                   elapsed_sec, mean_profit, median_tce, profitable_pct,
                   p10_profit, p90_profit, var_profit, std_profit,
                   total_iterations
            FROM simulation_runs
            ORDER BY run_id DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = [dict(r) for r in cur.fetchall()]
        con.close()
        return rows
    except Exception:
        return []


def get_iteration_profits(db_file: str, run_id: int) -> list:
    """Return (iteration, total_profit, avg_tce) for every iteration in a run."""
    try:
        con = sqlite3.connect(db_file)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute(
            """
            SELECT iteration, total_profit, avg_tce, n_voyages,
                   utilisation_pct, ballast_ratio
            FROM iteration_results
            WHERE run_id = ?
            ORDER BY iteration
            """,
            (run_id,),
        )
        rows = [dict(r) for r in cur.fetchall()]
        con.close()
        return rows
    except Exception:
        return []


def get_top_legs(db_file: str, run_id: int, programme_rank: int = 1) -> list:
    """Return all legs for a specific programme rank within a run."""
    try:
        con = sqlite3.connect(db_file)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute(
            """
            SELECT voyage_num, origin_port, dest_port, commodity,
                   freight_rate, cargo_mt, gross_freight, profit_loss,
                   laden_nm, ballast_nm, laden_days, ballast_days,
                   total_days, bunker_cost, port_costs
            FROM top_programme_legs
            WHERE run_id = ? AND programme_rank = ?
            ORDER BY voyage_num
            """,
            (run_id, programme_rank),
        )
        rows = [dict(r) for r in cur.fetchall()]
        con.close()
        return rows
    except Exception:
        return []
