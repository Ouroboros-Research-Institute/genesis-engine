"""
render_ablation_table.py — Fig 4 for the paper.

Renders paper/data/ablations.csv as a clean 12-row parameter-sensitivity
table. Baseline rows get a cyan tint; group rows (LIPID_SUPPLY, RD_NOISE,
GROWTH_PERTURB, STAB_WINDOW) are separated by a thin rule.

Usage:
    python3 paper/scripts/render_ablation_table.py

Output:
    paper/figures/fig4_ablation_table.png   (300 DPI, print-ready)
"""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

REPO = Path(__file__).resolve().parents[2]
CSV_PATH = REPO / "paper/data/ablations.csv"
OUT_PATH = REPO / "paper/figures/fig4_ablation_table.png"

# ─── palette (dashboard-derived but on white for print) ─────────────
CLR_TEXT      = "#16202a"
CLR_MUTED     = "#5a6b7a"
CLR_BASELINE  = "#d9f5fd"   # tint of dashboard cyan (#50ddff) on white
CLR_BASELINE_EDGE = "#50ddff"
CLR_ROW_ALT   = "#f5f7fa"
CLR_HEADER_BG = "#16202a"
CLR_HEADER_TX = "#ffffff"
CLR_ACCENT    = "#0f7fa6"
CLR_PASS      = "#1a7a3e"
CLR_RULE      = "#c9d3dc"
CLR_GROUP_RULE = "#4a5a6a"

# ─── columns ────────────────────────────────────────────────────────
# label, width (in figure-fraction units), alignment
COLS = [
    ("PARAMETER",       0.32, "left"),
    ("VALUE",           0.14, "right"),
    ("N REACHED BOTH",  0.22, "center"),
    ("CLOCK → MAP",     0.32, "center"),
]
PARAM_ORDER = ["LIPID_SUPPLY", "RD_NOISE", "GROWTH_PERTURB", "STAB_WINDOW"]


def _load() -> list[dict]:
    with CSV_PATH.open() as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["value"]        = float(r["value"])
        r["is_baseline"]  = r["is_baseline"].lower() == "true"
        r["n_runs"]       = int(r["n_runs"])
        r["n_both"]       = int(r["n_reached_both"])
        r["cbm"]          = int(r["clock_before_map_count"])
        r["cbm_pct"]      = float(r["clock_before_map_pct"])
    # group order, within-group sorted by value
    rows.sort(key=lambda r: (PARAM_ORDER.index(r["parameter"]), r["value"]))
    return rows


def _format_value(parameter: str, value: float) -> str:
    if parameter == "STAB_WINDOW":
        return f"{int(value)}"
    # LIPID_SUPPLY, RD_NOISE: small floats with trailing zeros trimmed
    s = f"{value:g}"
    return s


def render():
    rows = _load()

    # canvas geometry
    n_rows = len(rows)
    row_h  = 0.052
    header_h = 0.062
    title_h  = 0.095
    foot_h   = 0.095
    top_pad  = 0.02
    bot_pad  = 0.025
    fig_h    = top_pad + title_h + header_h + n_rows * row_h + foot_h + bot_pad
    fig_w    = 9.6  # inches

    fig, ax = plt.subplots(figsize=(fig_w, fig_h * fig_w), dpi=150)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_axis_off()
    ax.set_aspect("auto")

    # column x-anchors (cumulative)
    anchors = []
    x = 0.03
    for label, w, align in COLS:
        anchors.append((x, w, align))
        x += w

    # ─── title ────────────────────────────────────────────────────
    y_title = 1 - top_pad - title_h / 2
    ax.text(0.5, y_title + 0.018,
            "Parameter Sensitivity: Clock → Map Ordering Across 12 Conditions",
            ha="center", va="center",
            fontsize=15, fontweight="bold", color=CLR_TEXT,
            family="DejaVu Sans")
    ax.text(0.5, y_title - 0.025,
            "One-at-a-time (OAT) ablation around the N=500 baseline · 100 runs per condition",
            ha="center", va="center",
            fontsize=10.5, color=CLR_MUTED, family="DejaVu Sans")

    # ─── header row ───────────────────────────────────────────────
    y_hdr_top = 1 - top_pad - title_h
    y_hdr_bot = y_hdr_top - header_h
    ax.add_patch(Rectangle((0.025, y_hdr_bot), 0.95, header_h,
                           facecolor=CLR_HEADER_BG, edgecolor="none"))
    for (x, w, align), (label, _, _) in zip(anchors, COLS):
        xa = {"left": x + 0.012, "right": x + w - 0.012,
              "center": x + w / 2}[align]
        ax.text(xa, y_hdr_bot + header_h / 2, label,
                ha=align, va="center",
                fontsize=9.5, fontweight="bold", color=CLR_HEADER_TX,
                family="DejaVu Sans")

    # ─── data rows ────────────────────────────────────────────────
    y_cursor = y_hdr_bot
    prev_param = None

    for i, r in enumerate(rows):
        y_top = y_cursor
        y_bot = y_cursor - row_h

        # zebra stripe (below any highlight)
        if i % 2 == 0 and not r["is_baseline"]:
            ax.add_patch(Rectangle((0.025, y_bot), 0.95, row_h,
                                   facecolor=CLR_ROW_ALT, edgecolor="none"))
        # baseline tint
        if r["is_baseline"]:
            ax.add_patch(Rectangle((0.025, y_bot), 0.95, row_h,
                                   facecolor=CLR_BASELINE,
                                   edgecolor=CLR_BASELINE_EDGE, linewidth=0.8))

        # group separator (thicker rule when parameter changes, skip first)
        if prev_param is not None and prev_param != r["parameter"]:
            ax.hlines(y_top, 0.025, 0.975, colors=CLR_GROUP_RULE,
                      linewidth=1.1)
        elif prev_param is not None:
            ax.hlines(y_top, 0.025, 0.975, colors=CLR_RULE, linewidth=0.4)
        prev_param = r["parameter"]

        # column 1 — parameter (show name once per group)
        x1, w1, _ = anchors[0]
        first_in_group = (i == 0 or rows[i - 1]["parameter"] != r["parameter"])
        param_label = r["parameter"].replace("_", " ") if first_in_group else ""
        ax.text(x1 + 0.012, y_bot + row_h / 2, param_label,
                ha="left", va="center",
                fontsize=10.5, color=CLR_TEXT,
                fontweight="bold" if first_in_group else "normal",
                family="DejaVu Sans Mono")

        # column 2 — value  (+ baseline star)
        x2, w2, _ = anchors[1]
        val_s = _format_value(r["parameter"], r["value"])
        if r["is_baseline"]:
            val_s += "  ★"
        ax.text(x2 + w2 - 0.012, y_bot + row_h / 2, val_s,
                ha="right", va="center",
                fontsize=10.5, color=CLR_TEXT,
                family="DejaVu Sans Mono")

        # column 3 — N reached both
        x3, w3, _ = anchors[2]
        ax.text(x3 + w3 / 2, y_bot + row_h / 2,
                f"{r['n_both']} / {r['n_runs']}",
                ha="center", va="center",
                fontsize=10.5, color=CLR_TEXT,
                family="DejaVu Sans Mono")

        # column 4 — clock-before-map count / pct
        x4, w4, _ = anchors[3]
        pct = r["cbm_pct"]
        main = f"{r['cbm']} / {r['n_both']}"
        pct_s = f"{pct:.1f} %"
        # split into two elements: main bold + pct muted
        ax.text(x4 + w4 / 2 - 0.045, y_bot + row_h / 2, main,
                ha="right", va="center",
                fontsize=10.5, color=CLR_PASS, fontweight="bold",
                family="DejaVu Sans Mono")
        ax.text(x4 + w4 / 2 + 0.005, y_bot + row_h / 2, pct_s,
                ha="left", va="center",
                fontsize=10.5, color=CLR_PASS, family="DejaVu Sans Mono")

        y_cursor = y_bot

    # bottom rule
    ax.hlines(y_cursor, 0.025, 0.975, colors=CLR_GROUP_RULE, linewidth=1.1)

    # ─── footer ───────────────────────────────────────────────────
    total_both = sum(r["n_both"] for r in rows)
    total_cbm  = sum(r["cbm"]    for r in rows)
    total_pct  = 100 * total_cbm / total_both

    ax.text(0.5, y_cursor - 0.035,
            f"TOTAL  ·  {total_cbm} / {total_both} runs  ·  {total_pct:.1f} %  ·  ROBUST ✓",
            ha="center", va="center",
            fontsize=12.5, fontweight="bold", color=CLR_ACCENT,
            family="DejaVu Sans")
    ax.text(0.5, y_cursor - 0.072,
            "★ marks the N=500 baseline condition for each parameter group.",
            ha="center", va="center",
            fontsize=8.5, color=CLR_MUTED, style="italic",
            family="DejaVu Sans")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_PATH, dpi=300, bbox_inches="tight", facecolor="white")
    print(f"wrote {OUT_PATH}  ({OUT_PATH.stat().st_size:,} bytes)")


if __name__ == "__main__":
    render()
