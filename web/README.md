# Genesis Engine — Web Visualization

Zero-build, single-page web app for the Unified Trinity Framework simulation.

## Launch

```bash
cd ~/genesis-engine/web
./start.sh            # defaults to port 3000
./start.sh 8080       # custom port
```

Then open **http://localhost:3000** in a browser.

## Layout

- **index.html** — markup + layout for both views
- **style.css** — dark theme, monospace, scientific aesthetic
- **genesis.js** — JS port of `genesis_engine.py` (physics + canvas renderer)
- **app.js** — view switching, main loop, UI bindings
- **results.js** — loads `results/summary.csv` and renders MC stats
- **results/** — symlink to `~/genesis-engine/results/` (figures + CSVs)
- **start.sh** — `python3 -m http.server` launcher

## Physics parity

All constants in `genesis.js` mirror `genesis_engine.py` exactly:
`LIPID_SUPPLY=0.015`, `RD_NOISE=0.004`, `GROWTH_PERTURB=0.15`, `CRIT_THRESHOLD_MEAN=0.16 ± 0.015`,
`STAB_WINDOW=40`, `STAB_DEPTH=5`, phase thresholds (`B_CV=0.25`, `C_S=0.25`, `D_S=0.35`, `D_CV=0.3`, `D_GEN=5`).
EMA smoothing coefficient `0.12`, stability complexity gate (zero-crossings ≥ 4), temporal autocorrelation
across up to 5 historical snapshots. Division is pure geometric instability, not energy-gated. Metabolism
modulates only energy, not growth.
