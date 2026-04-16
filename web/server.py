#!/usr/bin/env python3
"""
GENESIS ENGINE — local dashboard server

Serves ~/genesis-engine/web/ as static files and exposes a single dynamic
endpoint, /api/status, for monitoring long-running background jobs from
the Monte Carlo tab (no more terminal-tailing).

Run:
    ./start.sh [port=3000]
or:
    python3 server.py [port]
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent
REPO = WEB_DIR.parent

# ── known log / result paths ────────────────────────────────────────
LOG_STAGE3 = Path("/tmp/stage3_test.log")
LOG_PILOT  = Path("/tmp/pilot_2d.log")
LOG_MC_2D  = Path("/tmp/mc_2d.log")
LOG_MC     = REPO / "mc_full.log"
ABL_SUMMARY = REPO / "results/ablations/ablation_summary.csv"
ABL_PER_RUN = REPO / "results/ablations/per_run"
ABL_TOTAL   = 12  # 4 params × 3 levels


# ── helpers ─────────────────────────────────────────────────────────
def _pgrep(needle: str) -> list[int]:
    """Return PIDs whose cmdline contains `needle`."""
    try:
        out = subprocess.check_output(
            ["pgrep", "-f", needle], text=True, stderr=subprocess.DEVNULL
        )
        return [int(x) for x in out.split() if x.strip().isdigit()]
    except subprocess.CalledProcessError:
        return []


def _read_tail(path: Path, n: int = 200) -> str:
    if not path.exists():
        return ""
    with path.open("rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        f.seek(max(0, size - 16_384))
        data = f.read().decode("utf-8", errors="replace")
    lines = data.splitlines()
    return "\n".join(lines[-n:])


def _last_match(text: str, pattern: str) -> str | None:
    m = None
    for line in text.splitlines():
        hit = re.search(pattern, line)
        if hit:
            m = hit
    return m.group(1) if m else None


# ── job inspectors ──────────────────────────────────────────────────
def job_stage3() -> dict:
    """2D sphere self-test (genesis_engine_2d.py __main__)."""
    alive = bool(_pgrep(r"genesis_engine_2d\.py"))
    tail = _read_tail(LOG_STAGE3)

    B = _last_match(tail, r"phase_B_tick:\s+(-?\d+)")
    C = _last_match(tail, r"phase_C_tick:\s+(-?\d+)")
    D = _last_match(tail, r"phase_D_tick:\s+(-?\d+)")
    final_phase = _last_match(tail, r"Final phase:\s+([ABCD])")
    current = _last_match(tail, r"t=\s*\d+\s+\|\s+pop=.*phase=([ABCD])")
    passed = "Stage 3 result: PASS" in tail

    if alive:
        status = "running"
    elif LOG_STAGE3.exists():
        status = "complete" + (" ✓" if passed else "")
    else:
        status = "not started"

    return {
        "name": "2D self-test",
        "status": status,
        "B_tick": int(B) if B is not None else None,
        "C_tick": int(C) if C is not None else None,
        "D_tick": int(D) if D is not None else None,
        "final_phase": final_phase,
        "current_phase": current,
        "log": str(LOG_STAGE3),
        "last_line": tail.splitlines()[-1] if tail else "",
    }


def job_ablation() -> dict:
    """Ablation study (run_ablations.py). Counts per_run CSVs."""
    alive = bool(_pgrep(r"run_ablations\.py"))
    done = 0
    if ABL_PER_RUN.exists():
        done = len([p for p in ABL_PER_RUN.iterdir() if p.suffix == ".csv"])

    has_summary = ABL_SUMMARY.exists()
    if alive:
        status = "running"
    elif has_summary and done >= ABL_TOTAL:
        status = "complete ✓"
    elif done > 0:
        status = "partial"
    else:
        status = "not started"

    return {
        "name": "Ablation study",
        "status": status,
        "conditions_done": done,
        "conditions_total": ABL_TOTAL,
        "has_summary": has_summary,
    }


def job_monte_carlo() -> dict:
    """Any Monte Carlo-style run (pilot_2d or full MC)."""
    # prefer the currently-running one; else the most-recent log
    candidates = [
        ("N=200 MC 2D",    LOG_MC_2D, r"run_monte_carlo_2d\.py"),
        ("N=10 pilot 2D",  LOG_PILOT, r"run_pilot_2d\.py"),
        ("N=500 MC 1D",    LOG_MC,    r"run_monte_carlo\.py"),
    ]
    chosen = None
    for label, path, proc_pat in candidates:
        if _pgrep(proc_pat):
            chosen = (label, path, True); break
    if chosen is None:
        # fall back to whichever log is newest
        live = [(l, p, False) for l, p, _ in candidates if p.exists()]
        if not live:
            return {"name": "Monte Carlo", "status": "not started",
                    "runs_done": 0, "runs_total": None}
        chosen = max(live, key=lambda t: t[1].stat().st_mtime)

    label, path, alive = chosen
    tail = _read_tail(path, n=1000)

    total = _last_match(tail, r"N=(\d+)")
    done  = sum(1 for ln in tail.splitlines() if re.match(r"\s*seed=", ln))
    passed = "PILOT: PASS" in tail or "PRECEDED MAP IN 100%" in tail

    if alive:
        status = "running"
    elif passed:
        status = "complete ✓"
    elif path.exists():
        status = "complete"
    else:
        status = "not started"

    return {
        "name": label,
        "status": status,
        "runs_done": done,
        "runs_total": int(total) if total else None,
        "log": str(path),
        "last_line": tail.splitlines()[-1] if tail else "",
    }


def build_status() -> dict:
    import datetime as dt
    return {
        "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
        "jobs": [
            job_stage3(),
            job_ablation(),
            job_monte_carlo(),
        ],
    }


# ── HTTP handler ────────────────────────────────────────────────────
class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kw):
        super().__init__(*args, directory=str(WEB_DIR), **kw)

    # silence default access log; keep errors
    def log_message(self, fmt, *args):
        if "404" in fmt % args or "500" in fmt % args:
            sys.stderr.write("[web] " + fmt % args + "\n")

    def do_GET(self):
        if self.path.split("?", 1)[0] == "/api/status":
            try:
                payload = json.dumps(build_status()).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except Exception as e:
                body = json.dumps({"error": str(e)}).encode()
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            return
        return super().do_GET()


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Genesis dashboard listening on http://localhost:{port}")
    print(f"  static root:  {WEB_DIR}")
    print(f"  status JSON:  http://localhost:{port}/api/status")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down.")
        srv.server_close()


if __name__ == "__main__":
    main()
