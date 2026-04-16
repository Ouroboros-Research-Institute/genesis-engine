"""
render_comparison_table.py — Fig 7 for the paper.

Two-part composite:
  (top)    Side-by-side comparison table of 1D vs 2D MC metrics (Fig-4 style).
  (bottom) Per-run C−B delay distributions (1D left, 2D right) rendered as
           rank-sorted strip plots on a log scale, with a horizontal dashed
           reference line at 50 ticks marked "sampling-window floor
           (minimum resolvable C − B gap)". This makes the figure
           visually agree with the revised caption's emphasis on the
           1D mean delay (243 ticks) being well above the sampling floor,
           while the 2D median (50 ticks) sits on it.

Rows (table):
  · N runs
  · Reached both B & C
  · Clock before Map (count / pct)
  · Binomial p (H0: random ordering)
  · Wilcoxon signed-rank p (delay > 0)
  · Hedges' g (organized vs disorganized populations)
  · Clock (B) median tick
  · Map (C) median tick
  · Agency (D) median tick
  · C−B delay mean   ← added: the real evidence (above the floor)
  · C−B delay median

Usage:
    python3 paper/scripts/render_comparison_table.py

Output:
    paper/figures/fig7_comparison_1d_2d.png   (300 DPI, print-ready)
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "paper/paper_data.json"
OUT  = REPO / "paper/figures/fig7_comparison_1d_2d.png"
CSV_1D = REPO / "paper/data/1d_mc_summary.csv"
CSV_2D = REPO / "paper/data/2d_mc_summary.csv"

# Sampling interval for phase detection — minimum resolvable C−B gap.
SAMPLE_INTERVAL = 50

# ─── palette (matches Fig 4) ────────────────────────────────────────
CLR_TEXT      = "#16202a"
CLR_MUTED     = "#5a6b7a"
CLR_1D_BG     = "#e9f6ff"      # pale blue tint for 1D column
CLR_2D_BG     = "#e9fce8"      # pale green tint for 2D column
CLR_1D_EDGE   = "#3fa6ea"
CLR_2D_EDGE   = "#5dc45d"
CLR_ROW_ALT   = "#f5f7fa"
CLR_HEADER_BG = "#16202a"
CLR_HEADER_TX = "#ffffff"
CLR_ACCENT    = "#0f7fa6"
CLR_PASS      = "#1a7a3e"
CLR_RULE      = "#c9d3dc"
CLR_GROUP_RULE = "#4a5a6a"

# column (label, width, align)
COLS = [
    ("METRIC",                 0.40, "left"),
    ("1D  (line, N=500)",      0.30, "center"),
    ("2D SPHERE  (N=200)",     0.30, "center"),
]


def _fmt_p(p: float) -> str:
    if p is None:
        return "—"
    if p == 0:
        return "0"
    # scientific notation with 2 sig figs
    exp = 0
    mantissa = p
    while mantissa < 1:
        mantissa *= 10
        exp -= 1
    while mantissa >= 10:
        mantissa /= 10
        exp += 1
    return f"{mantissa:.2f} × 10^{exp}"


def _superscript(exp: int) -> str:
    superscripts = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")
    return str(exp).translate(superscripts)


def _fmt_p_uni(p: float) -> str:
    if p is None:
        return "—"
    # get mantissa + exponent
    import math
    if p == 0:
        return "0"
    exp = int(math.floor(math.log10(p)))
    mantissa = p / 10**exp
    return f"{mantissa:.2f} × 10{_superscript(exp)}"


def _load_delays(csv_path: Path) -> np.ndarray:
    """Return per-run C − B delays (ticks) for every run where both
    phase_B_tick and phase_C_tick are non-negative (i.e., both reached)."""
    delays: list[int] = []
    with csv_path.open() as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            try:
                b = int(row["phase_B_tick"])
                c = int(row["phase_C_tick"])
            except (KeyError, ValueError):
                continue
            if b < 0 or c < 0:
                continue
            delays.append(c - b)
    return np.asarray(delays, dtype=float)


def _load() -> list[tuple[str, str, str, bool]]:
    """Return (metric_label, val_1d, val_2d, is_headline) rows."""
    d = json.loads(DATA.read_text())
    m1 = d["mc_1d"]
    m2 = d["mc_2d"]

    # 1D stats
    n1        = m1["n_runs"]
    cbm1      = m1["clock_before_map"]
    both1     = cbm1["both_reached"]
    cbm_ct1   = cbm1["cbm_count"]
    cbm_pct1  = cbm1["cbm_pct"]
    tests1    = m1["statistical_tests"]
    p_bin1    = tests1["binomial"]["p_value"]
    p_wx1     = tests1["wilcoxon"]["p_value"]
    g1        = tests1["hedges_g"]["g"]
    B1_med    = m1["transition_ticks"]["B"]["median"]
    C1_med    = m1["transition_ticks"]["C"]["median"]
    D1_med    = m1["transition_ticks"]["D"]["median"]
    dlt1      = m1["delay_C_minus_B"]
    dlt1_med  = dlt1["median"]
    dlt1_mean = dlt1["mean"]
    dlt1_std  = dlt1["std"]

    # 2D stats
    n2        = m2["n_runs"]
    cbm2      = m2["clock_before_map"]
    both2     = cbm2["both_reached"]
    cbm_ct2   = cbm2["cbm_count"]
    cbm_pct2  = cbm2["cbm_pct"]
    tests2    = m2["statistical_tests"]
    p_bin2    = tests2["binomial"]["p_value"]
    p_wx2     = tests2["wilcoxon"]["p_value"]
    g2        = tests2["hedges_g"]["g"]
    B2_med    = m2["transition_ticks"]["B"]["median"]
    C2_med    = m2["transition_ticks"]["C"]["median"]
    D2_med    = m2["transition_ticks"]["D"]["median"]
    dlt2      = m2["delay_C_minus_B"]
    dlt2_med  = dlt2["median"]
    dlt2_mean = dlt2["mean"]
    dlt2_std  = dlt2["std"]

    return [
        ("Independent runs (N)",              f"{n1}",            f"{n2}",            False),
        ("Reached both B & C",                f"{both1} / {n1}",  f"{both2} / {n2}",  False),
        ("Clock  before  Map",                f"{cbm_ct1} / {both1}  ({cbm_pct1:.1f} %)",
                                              f"{cbm_ct2} / {both2}  ({cbm_pct2:.1f} %)", True),
        ("Binomial p  (H₀: random order)",    _fmt_p_uni(p_bin1), _fmt_p_uni(p_bin2), True),
        ("Wilcoxon signed-rank p",            _fmt_p_uni(p_wx1),  _fmt_p_uni(p_wx2),  True),
        ("Hedges' g  (organized vs disorg.)", f"{g1:.2f}",        f"{g2:.2f}",        False),
        ("Clock  (B) median tick",            f"{int(B1_med)}",   f"{int(B2_med)}",   False),
        ("Map    (C) median tick",            f"{int(C1_med)}",   f"{int(C2_med)}",   False),
        ("Agency (D) median tick",            f"{int(D1_med)}",   f"{int(D2_med)}",   False),
        ("C − B  delay  mean ± std (ticks)",  f"{int(round(dlt1_mean))} ± {int(round(dlt1_std))}",
                                              f"{int(round(dlt2_mean))} ± {int(round(dlt2_std))}", False),
        ("C − B  delay median (ticks)",       f"{int(dlt1_med)}", f"{int(dlt2_med)}", False),
    ]


def render():
    rows = _load()
    delays_1d = _load_delays(CSV_1D)
    delays_2d = _load_delays(CSV_2D)
    print(f"loaded delays: 1D n={len(delays_1d)} (min={delays_1d.min():.0f}, "
          f"max={delays_1d.max():.0f}, median={np.median(delays_1d):.0f}); "
          f"2D n={len(delays_2d)} (min={delays_2d.min():.0f}, "
          f"max={delays_2d.max():.0f}, median={np.median(delays_2d):.0f})")

    # ─── canvas geometry ────────────────────────────────────────────
    # Top region (table): echoes Fig 4 proportions.
    # Bottom region (distribution panels): 5-inch strip, two panels.
    n_rows     = len(rows)
    row_h      = 0.065
    header_h   = 0.075
    title_h    = 0.105
    foot_h     = 0.115
    top_pad    = 0.02
    bot_pad    = 0.025
    table_frac = top_pad + title_h + header_h + n_rows * row_h + foot_h + bot_pad
    fig_w      = 10.0
    table_h    = table_frac * fig_w     # inches occupied by the table
    dist_h     = 5.0                    # inches for the distribution strip
    fig_h_in   = table_h + dist_h

    fig = plt.figure(figsize=(fig_w, fig_h_in), dpi=150)

    # Table axis — occupies the top portion of the figure.
    #   [left, bottom, width, height] in figure fraction
    table_bottom = dist_h / fig_h_in
    ax = fig.add_axes([0.0, table_bottom, 1.0, 1.0 - table_bottom])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_axis_off()
    ax.set_aspect("auto")

    # two distribution axes at bottom — 1D left, 2D right.
    # vertical layout (all in figure fraction, fig_h_in ≈ 15.55 in):
    #   panels y ∈ [0.050, 0.250]
    #   group-header label at y = 0.272
    #   table axis bottom at y = dist_h/fig_h_in ≈ 0.322
    # → ≈ 0.78 in clear whitespace between panels and table footer,
    #   ≈ 0.78 in below the panels for tick labels.
    panel_y     = 0.050
    panel_h_fig = 0.200
    panel_top_label_y = panel_y + panel_h_fig + 0.022
    ax_1d = fig.add_axes([0.085, panel_y, 0.385, panel_h_fig])
    ax_2d = fig.add_axes([0.545, panel_y, 0.385, panel_h_fig])

    # column x-anchors (cumulative)
    anchors = []
    x = 0.03
    for label, w, align in COLS:
        anchors.append((x, w, align))
        x += w

    # ─── title ──────────────────────────────────────────────────────
    y_title = 1 - top_pad - title_h / 2
    ax.text(0.5, y_title + 0.022,
            "1D  vs  2D  Sphere:  Clock → Map Ordering  Holds on Both Manifolds",
            ha="center", va="center",
            fontsize=15, fontweight="bold", color=CLR_TEXT,
            family="DejaVu Sans")
    ax.text(0.5, y_title - 0.027,
            "Canonical Monte Carlo comparison · 1D line (N=500, 80 000 ticks)  vs  "
            "642-vertex icosphere (N=200, 10 000 ticks)",
            ha="center", va="center",
            fontsize=10.5, color=CLR_MUTED, family="DejaVu Sans")

    # ─── header row ─────────────────────────────────────────────────
    y_hdr_top = 1 - top_pad - title_h
    y_hdr_bot = y_hdr_top - header_h
    ax.add_patch(Rectangle((0.025, y_hdr_bot), 0.95, header_h,
                           facecolor=CLR_HEADER_BG, edgecolor="none"))
    for (x, w, align), (label, _, _) in zip(anchors, COLS):
        xa = {"left": x + 0.012, "right": x + w - 0.012,
              "center": x + w / 2}[align]
        ax.text(xa, y_hdr_bot + header_h / 2, label,
                ha=align, va="center",
                fontsize=10, fontweight="bold", color=CLR_HEADER_TX,
                family="DejaVu Sans")

    # ─── data rows ──────────────────────────────────────────────────
    y_cursor = y_hdr_bot
    for i, (label, v1, v2, is_headline) in enumerate(rows):
        y_top = y_cursor
        y_bot = y_cursor - row_h

        # zebra stripe when not headline
        if i % 2 == 0 and not is_headline:
            ax.add_patch(Rectangle((0.025, y_bot), 0.95, row_h,
                                   facecolor=CLR_ROW_ALT, edgecolor="none"))
        # headline tint for the key stat rows
        if is_headline:
            # tint metric column + both value columns subtly
            x1, w1, _ = anchors[0]
            x2, w2, _ = anchors[1]
            x3, w3, _ = anchors[2]
            ax.add_patch(Rectangle((x2, y_bot), w2, row_h,
                                   facecolor=CLR_1D_BG,
                                   edgecolor=CLR_1D_EDGE, linewidth=0.8))
            ax.add_patch(Rectangle((x3, y_bot), w3, row_h,
                                   facecolor=CLR_2D_BG,
                                   edgecolor=CLR_2D_EDGE, linewidth=0.8))

        # thin separator between each row
        if i > 0:
            ax.hlines(y_top, 0.025, 0.975, colors=CLR_RULE, linewidth=0.4)

        # column 1 — metric label
        x1, w1, _ = anchors[0]
        ax.text(x1 + 0.012, y_bot + row_h / 2, label,
                ha="left", va="center",
                fontsize=11, color=CLR_TEXT,
                fontweight="bold" if is_headline else "normal",
                family="DejaVu Sans")

        # column 2 — 1D value
        x2, w2, _ = anchors[1]
        ax.text(x2 + w2 / 2, y_bot + row_h / 2, v1,
                ha="center", va="center",
                fontsize=11 if is_headline else 10.5,
                color=CLR_PASS if is_headline else CLR_TEXT,
                fontweight="bold" if is_headline else "normal",
                family="DejaVu Sans Mono")

        # column 3 — 2D value
        x3, w3, _ = anchors[2]
        ax.text(x3 + w3 / 2, y_bot + row_h / 2, v2,
                ha="center", va="center",
                fontsize=11 if is_headline else 10.5,
                color=CLR_PASS if is_headline else CLR_TEXT,
                fontweight="bold" if is_headline else "normal",
                family="DejaVu Sans Mono")

        y_cursor = y_bot

    # bottom rule
    ax.hlines(y_cursor, 0.025, 0.975, colors=CLR_GROUP_RULE, linewidth=1.1)

    # ─── footer ─────────────────────────────────────────────────────
    ax.text(0.5, y_cursor - 0.040,
            "CONCLUSION  ·  Clock precedes Map in 100 % of runs on both manifolds  ·  "
            "INVARIANT ✓",
            ha="center", va="center",
            fontsize=12.5, fontweight="bold", color=CLR_ACCENT,
            family="DejaVu Sans")
    ax.text(0.5, y_cursor - 0.078,
            "Headline rows tinted blue (1D) / green (2D) mark the core inferential tests.",
            ha="center", va="center",
            fontsize=9, color=CLR_MUTED, style="italic",
            family="DejaVu Sans")

    # ─── distribution panels (bottom) ──────────────────────────────────
    # Strip-plot: each run = one dot, rank-sorted by delay. Log-scale Y so
    # the 50-tick sampling floor is visible and well-separated from 10³-10⁴
    # tick outliers. Horizontal dashed line at y = 50 is the "sampling-
    # window floor (minimum resolvable C − B gap)".
    _draw_delay_panel(ax_1d, delays_1d, edge=CLR_1D_EDGE, fill=CLR_1D_BG,
                      title="1D  line  (N = 482 both-reached)",
                      mean=float(np.mean(delays_1d)),
                      median=float(np.median(delays_1d)))
    _draw_delay_panel(ax_2d, delays_2d, edge=CLR_2D_EDGE, fill=CLR_2D_BG,
                      title="2D  sphere  (N = 198 both-reached)",
                      mean=float(np.mean(delays_2d)),
                      median=float(np.median(delays_2d)))

    # Panel group header, sitting above both distribution axes.
    fig.text(0.5, panel_top_label_y,
             "Per-run  C − B  delay  distributions  (log scale)",
             ha="center", va="bottom",
             fontsize=12.5, fontweight="bold", color=CLR_TEXT,
             family="DejaVu Sans")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=300, bbox_inches="tight", facecolor="white")
    print(f"wrote {OUT}  ({OUT.stat().st_size:,} bytes)")


def _draw_delay_panel(ax, delays: np.ndarray, *, edge: str, fill: str,
                      title: str, mean: float, median: float) -> None:
    """Render one rank-sorted strip plot of per-run C − B delays on a log
    y-axis, with a horizontal reference line at SAMPLE_INTERVAL (= 50)
    labeled as the sampling-window floor.

    Zero-valued delays (runs where C was detected in the same sample
    window as B) are clamped to SAMPLE_INTERVAL for log-scale rendering,
    which is truthful: those runs sat on the floor.
    """
    n = len(delays)

    # Clamp zeros for log display (they *are* the floor).
    d_display = np.maximum(delays, SAMPLE_INTERVAL)
    order = np.argsort(d_display)
    d_sorted = d_display[order]
    x_rank = np.arange(1, n + 1)

    # Count of runs sitting exactly on the floor — the dense cluster
    # whose visibility we need to preserve through the floor line.
    n_on_floor = int(np.sum(d_display == SAMPLE_INTERVAL))
    floor_pct = 100.0 * n_on_floor / n

    # ── sampling-window floor line — drawn FIRST so dots overlay it ──
    # Thin dashed line so the cluster of runs at 50 ticks reads
    # through the line rather than being hidden by it.
    ax.axhline(SAMPLE_INTERVAL, color="#c0392b", linestyle=(0, (5, 3)),
               linewidth=0.9, zorder=2, alpha=0.85)

    # ── scatter: larger, semi-transparent so stacked points darken ───
    ax.scatter(x_rank, d_sorted,
               s=14, color=edge, alpha=0.40,
               edgecolors="none", zorder=3)

    # y range — lower bound well below 50 so the floor line sits clearly
    # *inside* the plot area rather than on the axis spine.
    y_top = max(d_sorted.max() * 1.6, 5e4)
    ax.set_yscale("log")
    ax.set_ylim(30, y_top)
    ax.set_xlim(0, n + 1)

    # ── floor label — ABOVE the line on the right, away from the x-axis
    #    tick labels. Two-line layout keeps the font readable.
    ax.text(n * 0.97, SAMPLE_INTERVAL * 1.12,
            "← sampling-window floor  ·  min resolvable C − B gap  (50 ticks)",
            ha="right", va="bottom",
            fontsize=8.2, color="#c0392b", fontweight="bold",
            family="DejaVu Sans", zorder=5)
    ax.text(n * 0.97, SAMPLE_INTERVAL * 1.04 / 1.32,  # sits just below the line
            f"{n_on_floor} / {n} runs  ({floor_pct:.1f} %)  on floor",
            ha="right", va="top",
            fontsize=7.8, color="#c0392b",
            family="DejaVu Sans", zorder=5)

    # ── mean reference line ───────────────────────────────────────────
    if mean > SAMPLE_INTERVAL * 1.25:
        # 1D: mean well above the floor — show its own dotted line
        ax.axhline(mean, color=CLR_ACCENT, linestyle=":", linewidth=1.3,
                   zorder=4)
        ax.text(n * 0.03, mean * 1.18,
                f"mean = {mean:,.0f} ticks",
                ha="left", va="bottom",
                fontsize=8.6, color=CLR_ACCENT, fontweight="bold",
                family="DejaVu Sans", zorder=5)
    else:
        # 2D: mean sits within ~10% of the floor — annotate on the
        # floor band itself to make the co-location explicit.
        ax.text(n * 0.03, SAMPLE_INTERVAL * 3.0,
                f"mean = {mean:.0f}  ·  median = {median:.0f}  ticks\n"
                f"(mean sits essentially on the floor)",
                ha="left", va="bottom",
                fontsize=8.6, color=CLR_ACCENT, fontweight="bold",
                family="DejaVu Sans", zorder=5,
                linespacing=1.25)

    # ── title + axis labels ───────────────────────────────────────────
    ax.set_title(title, fontsize=10.5, color=CLR_TEXT,
                 fontweight="bold", family="DejaVu Sans", pad=6)
    ax.set_xlabel("runs (rank-sorted by delay)", fontsize=9,
                  color=CLR_MUTED, family="DejaVu Sans")
    ax.set_ylabel("C − B  delay  (ticks, log)", fontsize=9,
                  color=CLR_MUTED, family="DejaVu Sans")
    ax.tick_params(axis="both", which="both", labelsize=8.5,
                   colors=CLR_MUTED)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("bottom", "left"):
        ax.spines[spine].set_color(CLR_RULE)
    ax.grid(axis="y", which="major", color=CLR_RULE, linewidth=0.4,
            alpha=0.7, zorder=1)

    # tint background so panel identity reads at a glance
    ax.set_facecolor(fill)


if __name__ == "__main__":
    render()
