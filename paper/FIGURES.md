# Master Figures List — Farina 2025

All stats lineage tracks back to `paper_data.json`. Raw per-run CSVs are in `data/`. PNGs live in `figures/`. This document is the single source of truth for what goes in the paper and where each panel comes from.

Legend for `status`:
- **ready**   — PNG is in `figures/`, regeneration script exists, numbers locked.
- **pending** — data exists, figure needs (re)generation.
- **blocked** — upstream run still in progress.

---

## Fig 1 · Phase transition time distributions
- **File:** `figures/fig1_phase_transitions.png`
- **Status:** ready
- **Source:** `results/summary.csv` (1D MC, N=500)
- **Script:** `analyze_results.py` (generate_figures → `phase_transitions.png`)
- **What it shows:** Overlaid histograms of `phase_B_tick`, `phase_C_tick`, `phase_D_tick` across all runs. Demonstrates that B (Clock) peaks at ~4200 ticks, C (Map) at ~4300, D (Agency) at ~5650 — with visibly ordered modes.
- **Caption stub:** "Transition-time distributions for the three sequential agency phases across N = 500 independent simulations. Clock (B) reliably precedes Map (C), which precedes Agency (D); medians 4 200 / 4 300 / 5 650 ticks."
- **Key numbers:** `paper_data.json → mc_1d.transition_ticks`

## Fig 2 · Clock vs Map (per-run scatter)
- **File:** `figures/fig2_clock_vs_map.png`
- **Status:** ready
- **Source:** `results/summary.csv` (1D MC, N=500)
- **Script:** `analyze_results.py` → `clock_vs_map.png`
- **What it shows:** Per-run `phase_B_tick` (x) vs `phase_C_tick` (y) scatter with the y=x diagonal. Every one of the 482 both-reached runs sits on/above the diagonal — the single most direct visual statement of the 100 % ordering result.
- **Caption stub:** "Per-run Clock transition vs Map transition. All 482 runs where both phases occurred fall on or above y = x (100 %; binomial p = 8.01 × 10⁻¹⁴⁶)."
- **Key numbers:** `paper_data.json → mc_1d.clock_before_map`, `.statistical_tests.binomial`

## Fig 3 · Example simulation traces
- **File:** `figures/fig3_example_timeseries.png`
- **Status:** ready
- **Source:** `results/timeseries/run_*.csv` (select a representative handful)
- **Script:** `analyze_results.py` → `example_timeseries.png`
- **What it shows:** Population, pattern-S, division-CV, and resource vs tick for a small grid of runs, with vertical lines marking each phase's transition tick. Makes the "CV collapses first, then S stabilizes" mechanism legible.
- **Caption stub:** "Example population traces with phase-transition markers. The division-regularity metric (CV) consistently breaks its ceiling before the pattern-stability metric (S) does."
- **Key numbers:** illustrative only.

## Fig 4 · Parameter sensitivity — ablation robustness table
- **File:** `figures/fig4_ablation_table.png`
- **Status:** ready
- **Source:** `paper/data/ablations.csv` (12 conditions × 100 runs)
- **Script:** `paper/scripts/render_ablation_table.py` (matplotlib, 300 DPI, print-ready white background; baseline rows highlighted cyan)
- **What it shows:** Parameter × value grid with CBM count / total-both and per-cell 100.0 %. All 12 conditions held at 100 %. The "robust" stamp.
- **Caption stub:** "Parameter sensitivity. The Clock → Map ordering holds in 1 165 / 1 165 runs (100 %) across four physics parameters varied over fold-change ranges of 1.7× – 4× around baseline."
- **Key numbers:** `paper_data.json → ablations.conditions[], .totals`

## Fig 5 · 2D sphere results
- **File:** `figures/fig5_2d_sphere_results.png`
- **Status:** ready
- **Source:** `results_2d/summary.csv` + `results_2d/timeseries/` (via `run_monte_carlo_2d.py -n 200 -t 10000 -w 16`)
- **Script:** `paper/scripts/render_2d_results.py` (matplotlib, 300 DPI, white background)
- **Layout:** four sub-panels (three conceptual) —
  1. (a) transition-time histograms (B / C / D),
  2. (b) per-run B vs C scatter with y=x diagonal + statistical annotation,
  3. (c) five example traces — pattern-stability S,
  4. (d) five example traces — division-regularity CV.
- **Caption stub:** "Clock → Map ordering replicates on a 642-vertex spherical manifold with cotangent Laplace-Beltrami diffusion. 198 of 198 runs where both phases occurred show Clock before Map (100 %; binomial p = 2.49 × 10⁻⁶⁰; Wilcoxon W = 19 701, p = 3.04 × 10⁻⁴⁴). Medians B = 4 900, C = 4 975, D = 5 850 ticks; C−B delay = 50 ticks (identical to 1D)."
- **Key numbers:** `paper_data.json → mc_2d.clock_before_map`, `.statistical_tests`, `.transition_ticks`

## Fig 6 · Dashboard screenshot — live simulation
- **File:** `figures/fig6_dashboard_screenshot.png`
- **Status:** ready
- **Source:** `web/` dashboard at `http://localhost:3000`, LIVE 1D tab.
- **Script:** `paper/scripts/capture_fig6_dashboard.py` (headless-chromium via Playwright; pauses the RAF loop, drives the sim directly via a `window.__genesis.stepN(n)` debug hook, auto-retries reset until Phase D is reached, then repaints + screenshots).
- **What it shows:** Organized cluster of ~30+ protocells (mostly cyan → pattern-stability S ≥ 0.55) in a single captured moment where all four phases have been reached. Sidebar reports population, S̄, CV, divisions, max-gen, and fully-populated B / C / D transition ticks. Sparklines show the CV crash and S climb. Companion methods figure — the framework is an interactive artifact, not just a batch job.
- **Caption stub:** "Live visualization dashboard. Real-time in-browser simulation of the Genesis 1D engine. The snapshot captures a post-Agency (D) state: 33 protocells, mean pattern-stability S = 0.98, max generation = 5, Clock / Map / Agency transition ticks 3 520 / 3 760 / 4 556."
- **Key numbers:** all qualitative except the on-screen B/C/D tick timestamps, which are illustrative of a single representative run.

## Fig 7 · 1D vs 2D comparison — table + delay distributions
- **File:** `figures/fig7_comparison_1d_2d.png`
- **Status:** ready
- **Source:** `paper/paper_data.json` (mc_1d + mc_2d blocks) + `paper/data/1d_mc_summary.csv` + `paper/data/2d_mc_summary.csv` (per-run C−B delays)
- **Script:** `paper/scripts/render_comparison_table.py` (matplotlib, 300 DPI, matches Fig 4 style)
- **Layout:** two-part composite —
  1. **(top) Comparison table.** Side-by-side metrics: N, reached-both, CBM count/pct, binomial-p, Wilcoxon-p, Hedges' g, median transition ticks (B, C, D), and C−B delay as both **mean ± std** and median. Headline rows (Clock before Map, binomial p, Wilcoxon p) tinted blue (1D) / green (2D).
  2. **(bottom) Per-run C−B delay distributions.** Two rank-sorted strip plots on a log y-axis (1D left, 2D right), each with:
     - A dashed red **horizontal reference line at 50 ticks** labeled *"sampling-window floor · min resolvable C − B gap (50 ticks)"* — marks the `SAMPLE_INTERVAL = 50` detection cadence below which no ordering claim is resolvable.
     - An on-panel count readout of how many runs sit exactly on the floor (1D: 434/482 ≈ 90 %; 2D: 193/198 ≈ 97.5 %).
     - A dotted accent-blue line at the mean. In 1D the mean (243 ticks) is well above the floor — the real evidence of a measurable delay. In 2D the mean (56 ticks) sits essentially on the floor and is labeled as such, making the "2D mean is sampling-limited" caveat visually self-evident.
- **Caption stub:** "Invariance of the Clock → Map ordering across manifolds. 1D line (N=500, 80 000 ticks) vs 642-vertex icosphere with cotangent Laplace-Beltrami diffusion (N=200, 40 000 ticks). Top: 100 % Clock-before-Map in both conditions, with overlapping median transition times. Bottom: per-run delay distributions on a log scale. The 1D **mean** C−B delay (243 ± 2 319 ticks) sits well above the 50-tick sampling floor and is the primary quantitative evidence. The 2D mean (56 ± 41 ticks) is close to the floor, so the 2D result supports replicability of the ordering but cannot tighten the magnitude estimate. Horizontal dashed line marks the `SAMPLE_INTERVAL = 50` detection cadence (minimum resolvable C − B gap)."
- **Key numbers:** `paper_data.json → mc_1d.*`, `mc_2d.*`; per-run delays from `paper/data/{1d,2d}_mc_summary.csv` columns `phase_B_tick`, `phase_C_tick`.

---

## Regeneration sources (so nothing becomes orphaned)

| Figure | Data source | Script | Output |
|---|---|---|---|
| 1 | `data/1d_mc_summary.csv` | `analyze_results.py` | `fig1_phase_transitions.png` |
| 2 | `data/1d_mc_summary.csv` | `analyze_results.py` | `fig2_clock_vs_map.png` |
| 3 | `results/timeseries/run_*.csv` | `analyze_results.py` | `fig3_example_timeseries.png` |
| 4 | `data/ablations.csv` | *(to write — scripts/render_ablation_table.py)* | `fig4_ablation_table.png` |
| 5 | `results_2d/summary.csv` (N=200, 10k ticks) + one snapshot | *(to write — scripts/render_2d_results.py)* | `fig5_2d_sphere_results.png` |
| 6 | dashboard (live 1D) | `paper/scripts/capture_fig6_dashboard.py` | `fig6_dashboard_screenshot.png` |
| 7 | `paper_data.json` (mc_1d + mc_2d) + `paper/data/1d_mc_summary.csv` + `paper/data/2d_mc_summary.csv` (per-run delays) | `paper/scripts/render_comparison_table.py` | `fig7_comparison_1d_2d.png` |
