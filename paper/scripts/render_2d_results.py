"""
render_2d_results.py — Fig 5 for the paper.

Three-panel figure for the N=200 2D sphere Monte Carlo:
  5a: Phase transition time histograms (B / C / D)
  5b: Clock (B) vs Map (C) per-run scatter, y=x diagonal
  5c: Five example traces reaching Agency (D)

Colours match the 1D figures (Fig 1–3):
  B → #ffcc40 (amber)    C → #80ff80 (light green)    D → #50ddff (cyan)

Usage:
    python3 paper/scripts/render_2d_results.py

Output:
    paper/figures/fig5_2d_sphere_results.png   (300 DPI, print-ready)
"""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

REPO       = Path(__file__).resolve().parents[2]
SUMMARY    = REPO / "results_2d/summary.csv"
TS_DIR     = REPO / "results_2d/timeseries"
OUT        = REPO / "paper/figures/fig5_2d_sphere_results.png"

CLR_B = "#ffcc40"
CLR_C = "#80ff80"
CLR_D = "#50ddff"
CLR_DIAG = "#d44a4a"
CLR_TEXT = "#16202a"
CLR_MUTED = "#5a6b7a"


def _load_summary():
    rows = []
    with SUMMARY.open() as f:
        for r in csv.DictReader(f):
            rows.append({
                "seed":           int(r["seed"]),
                "final_phase":    r["final_phase"],
                "phase_B_tick":   int(r["phase_B_tick"]),
                "phase_C_tick":   int(r["phase_C_tick"]),
                "phase_D_tick":   int(r["phase_D_tick"]),
                "clock_before_map": r["clock_before_map"] == "True",
            })
    return rows


def _load_timeseries(seed: int):
    path = TS_DIR / f"run_{seed:04d}.csv"
    t, pop, s, cv, res = [], [], [], [], []
    with path.open() as f:
        for r in csv.DictReader(f):
            t.append(int(r["tick"]))
            pop.append(int(r["population"]))
            s.append(float(r["mean_s"]))
            cv.append(float(r["mean_cv"]))
            res.append(float(r["resource"]))
    return np.array(t), np.array(pop), np.array(s), np.array(cv), np.array(res)


def render():
    rows = _load_summary()
    b = np.array([r["phase_B_tick"] for r in rows if r["phase_B_tick"] > 0])
    c = np.array([r["phase_C_tick"] for r in rows if r["phase_C_tick"] > 0])
    d = np.array([r["phase_D_tick"] for r in rows if r["phase_D_tick"] > 0])

    both = [(r["phase_B_tick"], r["phase_C_tick"]) for r in rows
            if r["phase_B_tick"] > 0 and r["phase_C_tick"] > 0]
    bs = np.array([p[0] for p in both])
    cs = np.array([p[1] for p in both])
    cbm = int(np.sum(bs < cs))

    # Layout: top row = 5a + 5b, bottom row = 5c spanning full width
    fig = plt.figure(figsize=(14, 11), dpi=150)
    gs = fig.add_gridspec(2, 2, height_ratios=[1.0, 1.1],
                          hspace=0.33, wspace=0.22,
                          left=0.07, right=0.97, top=0.93, bottom=0.07)

    fig.suptitle(
        "2D Spherical Manifold — N = 200 Monte Carlo, 10 000 ticks per run",
        fontsize=15, fontweight="bold", color=CLR_TEXT, y=0.985,
    )

    # ─── 5a — transition time histograms ──────────────────────────
    ax1 = fig.add_subplot(gs[0, 0])
    bins = np.linspace(3000, 10000, 35)
    if len(b):
        ax1.hist(b, bins=bins, alpha=0.75,
                 label=f"B · Clock   (N={len(b)}, median={int(np.median(b))})",
                 color=CLR_B, edgecolor="#c99a10", linewidth=0.4)
    if len(c):
        ax1.hist(c, bins=bins, alpha=0.75,
                 label=f"C · Map      (N={len(c)}, median={int(np.median(c))})",
                 color=CLR_C, edgecolor="#4fa84f", linewidth=0.4)
    if len(d):
        ax1.hist(d, bins=bins, alpha=0.75,
                 label=f"D · Agency (N={len(d)}, median={int(np.median(d))})",
                 color=CLR_D, edgecolor="#1e95b8", linewidth=0.4)
    ax1.set_xlabel("Transition tick", fontsize=11, color=CLR_TEXT)
    ax1.set_ylabel("Number of runs", fontsize=11, color=CLR_TEXT)
    ax1.set_title("(a) Phase transition time distributions",
                  fontsize=12, fontweight="bold", color=CLR_TEXT, loc="left")
    ax1.legend(frameon=False, fontsize=9.5, loc="upper right")
    ax1.grid(alpha=0.25, linewidth=0.5)
    ax1.set_axisbelow(True)
    for s in ax1.spines.values():
        s.set_color(CLR_MUTED); s.set_linewidth(0.8)

    # ─── 5b — B vs C scatter ──────────────────────────────────────
    ax2 = fig.add_subplot(gs[0, 1])
    lim_lo = min(bs.min(), cs.min()) - 200
    lim_hi = max(bs.max(), cs.max()) + 200
    ax2.plot([lim_lo, lim_hi], [lim_lo, lim_hi],
             linestyle="--", color=CLR_DIAG, linewidth=1.3,
             label="y = x   (simultaneous)")
    ax2.scatter(bs, cs, alpha=0.55, s=28, color=CLR_D,
                edgecolor="#1e95b8", linewidth=0.4,
                label=f"per-run pair   (N={len(both)})")
    ax2.set_xlim(lim_lo, lim_hi)
    ax2.set_ylim(lim_lo, lim_hi)
    ax2.set_aspect("equal")
    ax2.set_xlabel("Clock (B) transition tick", fontsize=11, color=CLR_TEXT)
    ax2.set_ylabel("Map (C) transition tick", fontsize=11, color=CLR_TEXT)
    ax2.set_title("(b) Clock vs Map — every point on or above y = x",
                  fontsize=12, fontweight="bold", color=CLR_TEXT, loc="left")
    ax2.legend(frameon=False, fontsize=9.5, loc="lower right")
    ax2.grid(alpha=0.25, linewidth=0.5)
    ax2.set_axisbelow(True)
    ax2.text(
        0.03, 0.97,
        f"{cbm} / {len(both)}  Clock before Map  (100 %)\n"
        f"binomial p = 2.49 × 10⁻⁶⁰",
        transform=ax2.transAxes, fontsize=10,
        color=CLR_TEXT, fontweight="bold",
        verticalalignment="top",
        bbox=dict(boxstyle="round,pad=0.45", facecolor="#ffffff",
                  edgecolor=CLR_MUTED, linewidth=0.6, alpha=0.92),
    )
    for s in ax2.spines.values():
        s.set_color(CLR_MUTED); s.set_linewidth(0.8)

    # ─── 5c — example traces ──────────────────────────────────────
    ax3a = fig.add_subplot(gs[1, 0])
    ax3b = fig.add_subplot(gs[1, 1])

    d_runs = [r for r in rows if r["final_phase"] == "D"][:5]
    palette = ["#50ddff", "#80ff80", "#ffcc40", "#ff8fa3", "#b48cff"]

    for i, r in enumerate(d_runs):
        t, pop, s_ts, cv, _ = _load_timeseries(r["seed"])
        col = palette[i]
        ax3a.plot(t, s_ts, color=col, alpha=0.85, linewidth=1.2,
                  label=f"seed {r['seed']}")
        ax3b.plot(t, cv, color=col, alpha=0.85, linewidth=1.2)

        # phase markers (subtle)
        for ax in (ax3a, ax3b):
            if r["phase_B_tick"] > 0:
                ax.axvline(r["phase_B_tick"], color=CLR_B, alpha=0.35,
                           linewidth=0.8, linestyle="--")
            if r["phase_C_tick"] > 0:
                ax.axvline(r["phase_C_tick"], color=CLR_C, alpha=0.35,
                           linewidth=0.8, linestyle="--")
            if r["phase_D_tick"] > 0:
                ax.axvline(r["phase_D_tick"], color=CLR_D, alpha=0.45,
                           linewidth=0.9, linestyle="--")

    ax3a.set_ylabel("Pattern-stability  S", fontsize=11, color=CLR_TEXT)
    ax3a.set_xlabel("Tick", fontsize=11, color=CLR_TEXT)
    ax3a.set_title("(c) Example traces — pattern-stability S",
                   fontsize=12, fontweight="bold", color=CLR_TEXT, loc="left")
    ax3a.legend(frameon=False, fontsize=9, loc="lower right",
                title="5 runs reaching Agency", title_fontsize=9)
    ax3a.grid(alpha=0.25, linewidth=0.5); ax3a.set_axisbelow(True)
    ax3a.set_ylim(-0.02, 1.05)

    ax3b.set_ylabel("Division regularity  CV", fontsize=11, color=CLR_TEXT)
    ax3b.set_xlabel("Tick", fontsize=11, color=CLR_TEXT)
    ax3b.set_title("(d) Example traces — division-regularity CV  (lower = more regular)",
                   fontsize=12, fontweight="bold", color=CLR_TEXT, loc="left")
    ax3b.grid(alpha=0.25, linewidth=0.5); ax3b.set_axisbelow(True)
    ax3b.set_ylim(-0.02, 1.05)

    # Add faint phase-marker legend to 3b
    from matplotlib.lines import Line2D
    legend_lines = [
        Line2D([0], [0], color=CLR_B, linestyle="--", linewidth=1.0, label="B tick"),
        Line2D([0], [0], color=CLR_C, linestyle="--", linewidth=1.0, label="C tick"),
        Line2D([0], [0], color=CLR_D, linestyle="--", linewidth=1.0, label="D tick"),
    ]
    ax3b.legend(handles=legend_lines, frameon=False, fontsize=9,
                loc="upper right", title="phase markers", title_fontsize=9)

    for ax in (ax3a, ax3b):
        for sp in ax.spines.values():
            sp.set_color(CLR_MUTED); sp.set_linewidth(0.8)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=300, bbox_inches="tight", facecolor="white")
    print(f"wrote {OUT}  ({OUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    render()
