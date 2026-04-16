# Genesis Engine

**Sequential Assembly of Biological Agency: Division Regularity Precedes Pattern Stability in Evolving Protocells**

[![SSRN](https://img.shields.io/badge/Preprint-SSRN-blue)](https://papers.ssrn.com)
[![Dashboard](https://img.shields.io/badge/Live%20Dashboard-genesis--engine.lucyvpa.com-brightgreen)](https://genesis-engine.lucyvpa.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org)

---

## Abstract

The origin of biological agency requires the coordinated emergence of three
sub-systems — a **Clock** (metabolic rhythm driving division), a **Map**
(stable spatial patterning), and an **Engine** (thermodynamic coupling that
exports entropy). We ask whether these sub-systems must appear in a specific
order, or whether any ordering suffices. Across **500** independent 1D Monte
Carlo runs and **200** independent 2D runs on a spherical manifold (642-vertex
icosphere, cotangent Laplace–Beltrami operator), the Clock phase preceded
the Map phase in **1,165 of 1,165 runs** where both transitions occurred
(**100 %**; combined binomial *p* < 10⁻²⁰⁰; Hedges' *g* = 6.34). Twelve
ablation conditions spanning factor-of-2 perturbations of lipid supply,
reaction-diffusion noise, growth perturbation, and stability window each
preserved 100 % Clock-before-Map ordering. The ordering is topology- and
parameter-invariant: pattern formation is a **filter on top of a running
Clock**, not a parallel process. These findings reframe abiogenesis as the
sequential assembly of necessary preconditions rather than the simultaneous
emergence of all capabilities.

## Key Result

> **Clock always precedes Map. 1,165 / 1,165 = 100 %. Zero violations.**
>
> 1D: *p* = 8.01 × 10⁻¹⁴⁶, Hedges' *g* = 9.41
> 2D: *p* = 2.49 × 10⁻⁶⁰, Hedges' *g* = 3.27
> Combined: *p* < 10⁻²⁰⁰, *g* = 6.34

---

## Repository Layout

```
genesis-engine/
├── genesis_engine.py          # 1D reaction-diffusion engine + protocell dynamics
├── genesis_engine_2d.py       # 2D spherical-manifold engine (icosphere + LB operator)
├── mesh_utils.py              # Icosphere subdivision, cotangent Laplace-Beltrami, sparse CSR
├── run_monte_carlo.py         # 1D Monte Carlo driver (N=500)
├── run_monte_carlo_2d.py      # 2D Monte Carlo driver (N=200)
├── run_pilot_2d.py            # 2D PASS/FAIL gate (N=10) run before overnight
├── run_ablations.py           # Twelve-condition ablation grid (N=100 × 12)
├── calibrate_2d.py            # α* sweep for 2D ↔ 1D statistical calibration
├── analyze_results.py         # Aggregate summaries, Hedges' g, binomial + Wilcoxon
│
├── paper/                     # Manuscript, figures, canonical aggregate data
│   ├── genesis_paper_v3.md    # Source markdown (latest revision)
│   ├── paper_data.json        # Single source of truth for all numerical claims
│   ├── FIGURES.md             # Caption and provenance for all 7 figures
│   ├── figures/               # fig1 … fig7 (PNG, archival resolution)
│   ├── scripts/               # Figure-generation scripts
│   └── submission/            # SSRN-formatted PDF + LaTeX source + .bib
│
├── web/                       # Interactive dashboard (static HTML + JS)
│   ├── index.html             # Three tabs: 1D live, 2D sphere live, results
│   ├── genesis.js             # 1D engine (JS port of genesis_engine.py)
│   ├── genesis_2d.js          # 2D sphere engine (JS port of genesis_engine_2d.py)
│   ├── icosphere.js           # Browser-side mesh builder
│   ├── app.js                 # UI glue: tabs, controls, charts
│   ├── results.js             # Monte Carlo tab — loads paper/paper_data.json
│   ├── style.css
│   ├── server.py              # Optional local server (adds /api/status; not needed for static hosting)
│   └── start.sh               # Convenience launcher
│
├── results/                   # 1D Monte Carlo raw + aggregate outputs
│   ├── summary.csv            # N=500 per-run metrics
│   ├── timeseries/            # Per-run time-series CSVs
│   ├── ablations/             # 12-condition ablation outputs
│   └── figures/               # Diagnostic figures
│
└── results_2d/                # 2D Monte Carlo raw + aggregate outputs
    ├── summary.csv            # N=200 per-run metrics
    └── timeseries/
```

---

## Quickstart

Requires Python 3.10 or newer.

```bash
git clone https://github.com/Ouroboros-Research-Institute/genesis-engine.git
cd genesis-engine
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### Run a single 1D simulation

```bash
python3 genesis_engine.py
```

### Launch the live dashboard

```bash
cd web && ./start.sh          # serves http://localhost:3000
```

Open `http://localhost:3000` in any modern browser. Three tabs:

- **1D Live Simulation** — reaction-diffusion on a 1D genome, canvas-rendered
  with latched phase transitions and live stats.
- **2D Sphere** — icosphere surface rendering with up to 30 simultaneous
  protocells, each tracked through its own Clock/Map transitions.
- **Monte Carlo Results** — aggregate statistics loaded directly from
  `paper/paper_data.json`.

---

## Reproducing the Paper Results

### 1. 1D Monte Carlo (N = 500, ~8 min on 16 workers)

```bash
python3 run_monte_carlo.py -n 500 -t 80000 -w 16
python3 analyze_results.py results/summary.csv
```

### 2. 2D Monte Carlo (N = 200, ~30 min on 16 workers)

```bash
python3 run_pilot_2d.py                         # PASS/FAIL gate first
python3 run_monte_carlo_2d.py -n 200 -t 40000 -w 16
python3 analyze_results.py results_2d/summary.csv
```

### 3. Ablations (N = 100 × 12 conditions, ~20 min)

```bash
python3 run_ablations.py
```

### 4. Regenerate figures

```bash
cd paper/scripts
python3 render_phase_transitions.py
python3 render_clock_vs_map.py
python3 render_example_timeseries.py
python3 render_ablation_table.py
python3 render_2d_sphere_results.py
python3 capture_fig6_dashboard.py        # requires playwright; live server must be running
python3 render_comparison_table.py
```

### 5. Rebuild the manuscript PDF

```bash
cd paper/submission
tectonic -X compile genesis_paper_farina_2026.tex
```

---

## Canonical Parameters

All shared between 1D and 2D engines unless noted:

| Parameter          | Value   | Role                                      |
|--------------------|---------|-------------------------------------------|
| `MIN_RADIUS`       | 8.0     | Min protocell radius (division gate)      |
| `LIPID_SUPPLY`     | 0.015   | Ambient lipid accumulation rate           |
| `RD_NOISE`         | 0.004   | Reaction-diffusion stochastic amplitude   |
| `PHASE_B_CV`       | 0.25    | Division-regularity (Clock) CV threshold  |
| `SAMPLE_INTERVAL`  | 50      | Tick interval for phase-metric sampling   |
| `STAB_WINDOW`      | 40      | Window size for pattern stability metric  |
| `PHASE_D_GEN`      | 5       | Generations required to latch Phase D     |
| `ALPHA_RESCALE`    | 0.40    | 2D-only; empirically calibrated to match 1D |
| `RD_STEPS`         | 90      | 2D-only; RD substeps per simulation tick  |

The 2D mesh is an **icosphere, subdivision = 3** → **642 vertices, 1,280 faces**.
The Laplacian is the **cotangent Laplace–Beltrami operator**, stored as a
**sparse CSR** with 4,482 non-zeros.

---

## Citation

```bibtex
@article{farina2026genesis,
  author  = {Farina, Micka{\"e}l},
  title   = {Sequential Assembly of Biological Agency: Division Regularity Precedes Pattern Stability in Evolving Protocells},
  journal = {SSRN Electronic Journal},
  year    = {2026},
  url     = {https://papers.ssrn.com},
}
```

See [`CITATION.cff`](CITATION.cff) for machine-readable metadata.

---

## Contact

**Mickaël Farina**
AVADSA Consulting LLC
1712 Pioneer Ave, Suite 2011
Cheyenne, WY 82001, USA
D-U-N-S: 136864260
Email: mickaelfarinavance@yahoo.com

---

## License

Released under the [MIT License](LICENSE). You are free to use, modify, and
redistribute the code and data. If you reproduce the scientific results in
an academic context, please cite the paper.
