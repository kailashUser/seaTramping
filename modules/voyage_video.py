"""
Serve the 3D voyage renderer to the Streamlit app.

The renderer is an ES module that fetches three.js, coastlines and a timeline
over HTTP. Streamlit's components.html drops markup into a sandboxed srcdoc
iframe with no usable base URL, so relative fetches there fail. Instead a small
static server runs alongside the app and the tab embeds an iframe pointing at
it.

The server starts once per Streamlit session via cache_resource and stays up
for the life of the process.

    from modules.voyage_video import render_voyage_video
    render_voyage_video(run_id=None)      # None = latest run in the DB
"""

import json
import os
import socket
import subprocess
import sys
import time

from modules.voyage_timeline import build_timeline, latest_run_id

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
RENDERER_DIR = os.path.join(_ROOT, "renderer")
DATA_DIR = os.path.join(RENDERER_DIR, "data")

DEFAULT_PORT = 8781


def _port_in_use(port, host="127.0.0.1"):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.25)
        return s.connect_ex((host, port)) == 0


def ensure_server(port=DEFAULT_PORT, timeout=6.0):
    """
    Start the static server if nothing is already listening. Returns base URL.

    Deliberately a separate PROCESS, not a thread. Streamlit tracks a per-script
    run context across threads, and a long-lived thread started from inside a
    script run can upset its session bookkeeping ("Tried to use SessionInfo
    before it was initialized"). A subprocess shares nothing with the Streamlit
    runtime, so it cannot interfere.
    """
    if _port_in_use(port):
        return f"http://127.0.0.1:{port}"

    script = os.path.join(RENDERER_DIR, "capture_server.py")
    creationflags = 0
    if os.name == "nt":
        # Detach so the server is not killed when Streamlit reruns the script,
        # and so no console window appears.
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | \
                        getattr(subprocess, "DETACHED_PROCESS", 0)

    subprocess.Popen(
        [sys.executable, script, str(port)],
        cwd=_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )

    deadline = time.time() + timeout
    while time.time() < deadline:
        if _port_in_use(port):
            return f"http://127.0.0.1:{port}"
        time.sleep(0.15)

    raise RuntimeError(
        f"Voyage video server did not start on port {port}. "
        f"Start it manually: python renderer/capture_server.py {port}"
    )


def write_timeline(run_id=None, programme_rank=1):
    """
    Build the timeline for a run and write it where the renderer can fetch it.

    Returns (relative_url, timeline). Raises ValueError when the DB holds no
    run with stored programme legs.
    """
    if run_id is None:
        run_id = latest_run_id()
        if run_id is None:
            raise ValueError(
                "No simulation runs stored yet — run a simulation first."
            )

    timeline = build_timeline(run_id=run_id, programme_rank=programme_rank)
    os.makedirs(DATA_DIR, exist_ok=True)
    name = f"timeline_run{run_id}_r{programme_rank}.json"
    with open(os.path.join(DATA_DIR, name), "w", encoding="utf-8") as f:
        json.dump(timeline, f, separators=(",", ":"))
    return f"./data/{name}", timeline


def viewer_url(timeline_rel, base, minsec=4, maxsec=6, portsec=2, herosec=8):
    from urllib.parse import urlencode
    q = urlencode({
        "timeline": timeline_rel,
        "minsec": minsec, "maxsec": maxsec,
        "portsec": portsec, "herosec": herosec,
    })
    return f"{base}/renderer/voyage3d.html?{q}"


def estimate_runtime(timeline, minsec=4, maxsec=6, portsec=2, herosec=8, heroes=3):
    """Mirror of the renderer's pacing maths, so the UI can show runtime up front."""
    segs = timeline["segments"]
    ports = sorted(
        [(i, s) for i, s in enumerate(segs) if s["type"] == "port"],
        key=lambda t: -t[1]["days"],
    )
    hero_idx = {i for i, _ in ports[:heroes]}
    nms = [s["nm"] for s in segs if s["type"] != "port"]
    if not nms:
        return 0.0
    lo, hi = min(nms), max(nms)

    total = 0.0
    for i, s in enumerate(segs):
        if s["type"] == "port":
            total += herosec if i in hero_idx else portsec
        else:
            f = (s["nm"] - lo) / (hi - lo) if hi > lo else 0.5
            total += minsec + (maxsec - minsec) * f
    return total
