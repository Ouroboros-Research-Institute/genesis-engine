"""
rebuild_paper_data.py — recompute paper/paper_data.json from the raw CSVs.

Re-run this whenever a Monte Carlo completes or ablations change. Keeps a
single source of truth so the manuscript sentence and all summary tables
can be regenerated without hand-editing JSON.

Usage:
    cd ~/genesis-engine
    python3 paper/scripts/rebuild_paper_data.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
from scipy import stats as sp

REPO   = Path(__file__).resolve().parents[2]
PAPER  = REPO / "paper"
DATA   = PAPER / "data"

MC_1D_CSV   = REPO / "results/summary.csv"
MC_2D_CSV   = REPO / "results_2d/summary.csv"
ABL_CSV     = REPO / "results/ablations/ablation_summary.csv"
PILOT_LOG   = Path("/tmp/pilot_2d.log")  # advisory only
OUT_JSON    = PAPER / "paper_data.json"


def _load_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open() as f:
        return list(csv.DictReader(f))


def _hedges_g(a: list[int], b: list[int]) -> tuple[float, int, int]:
    a, b = np.asarray(a, float), np.asarray(b, float)
    n1, n2 = len(a), len(b)
    if n1 < 2 or n2 < 2:
        return float("nan"), n1, n2
    m1, m2 = a.mean(), b.mean()
    s1, s2 = a.std(ddof=1), b.std(ddof=1)
    sp_ = np.sqrt(((n1 - 1) * s1 * s1 + (n2 - 1) * s2 * s2) / (n1 + n2 - 2))
    d = (m1 - m2) / sp_ if sp_ > 0 else 0.0
    J = 1 - 3 / (4 * (n1 + n2) - 9)
    return float(d * J), n1, n2


def compute_mc_block(rows: list[dict], label: str, source: str) -> dict:
    """Produce the canonical mc_* block for the given Monte Carlo CSV."""
    if not rows:
        return {"status": "pending", "source_planned": source, "placeholders": True}

    n = len(rows)
    phases = [r["final_phase"] for r in rows]
    reached_B = [int(r["phase_B_tick"]) for r in rows if int(r["phase_B_tick"]) > 0]
    reached_C = [int(r["phase_C_tick"]) for r in rows if int(r["phase_C_tick"]) > 0]
    reached_D = [int(r["phase_D_tick"]) for r in rows if int(r["phase_D_tick"]) > 0]
    both = [(int(r["phase_B_tick"]), int(r["phase_C_tick"])) for r in rows
            if int(r["phase_B_tick"]) > 0 and int(r["phase_C_tick"]) > 0]

    cbm = sum(1 for b, c in both if b < c)
    diffs = np.array([c - b for b, c in both]) if both else np.array([])

    p_binom = float(sp.binomtest(cbm, len(both), 0.5, alternative="greater").pvalue) \
              if both else float("nan")
    if diffs.size:
        W, p_wx = sp.wilcoxon(diffs, alternative="greater")
    else:
        W, p_wx = float("nan"), float("nan")

    pop_org = [int(r["final_pop"]) for r in rows if float(r["final_mean_s"]) > 0.3]
    pop_dis = [int(r["final_pop"]) for r in rows if float(r["final_mean_s"]) < 0.1]
    g, n_org, n_dis = _hedges_g(pop_org, pop_dis)

    def _stats(arr):
        if not arr: return None
        a = np.asarray(arr)
        return {"mean": float(a.mean()), "median": float(np.median(a)),
                "std": float(a.std(ddof=1))}

    return {
        "source": source,
        "n_runs": n,
        "max_ticks_per_run": int(rows[0]["max_ticks"]),
        "reached": {"B": len(reached_B), "C": len(reached_C), "D": len(reached_D)},
        "final_phase_distribution": {p: phases.count(p) for p in "ABCD"},
        "clock_before_map": {
            "both_reached": len(both),
            "cbm_count":    cbm,
            "cbm_pct":      100 * cbm / len(both) if both else None,
            "violations":   len(both) - cbm,
        },
        "transition_ticks": {
            "B": _stats(reached_B),
            "C": _stats(reached_C),
            "D": _stats(reached_D),
        },
        "delay_C_minus_B": (
            {"mean": float(diffs.mean()), "median": float(np.median(diffs)),
             "std": float(diffs.std(ddof=1)), "unit": "ticks"}
            if diffs.size else None
        ),
        "statistical_tests": {
            "binomial": {"p_value": p_binom},
            "wilcoxon": {"W_statistic": float(W) if W == W else None, "p_value": float(p_wx) if p_wx == p_wx else None},
            "hedges_g": {"g": g, "n_organized": n_org, "n_disorganized": n_dis},
        },
    }


def compute_ablations_block() -> dict:
    rows = _load_rows(ABL_CSV)
    if not rows:
        return {"status": "missing"}
    conds = []
    for r in rows:
        conds.append({
            "parameter":   r["parameter"],
            "value":       float(r["value"]),
            "is_baseline": r["is_baseline"].lower() == "true",
            "n_runs":      int(r["n_runs"]),
            "n_both":      int(r["n_reached_both"]),
            "cbm_count":   int(r["clock_before_map_count"]),
            "cbm_pct":     float(r["clock_before_map_pct"]),
            "mean_delay":  float(r["mean_delay"]),
        })
    total_both = sum(c["n_both"] for c in conds)
    total_cbm  = sum(c["cbm_count"] for c in conds)
    return {
        "source": str(ABL_CSV),
        "n_runs_per_condition": conds[0]["n_runs"],
        "totals": {
            "total_conditions":    len(conds),
            "total_runs":          sum(c["n_runs"] for c in conds),
            "total_both_reached":  total_both,
            "total_cbm":           total_cbm,
            "cbm_pct_overall":     100 * total_cbm / total_both if total_both else None,
        },
        "conditions": conds,
    }


def main():
    existing = json.loads(OUT_JSON.read_text()) if OUT_JSON.exists() else {}

    mc_1d = compute_mc_block(_load_rows(MC_1D_CSV),
                             "mc_1d", f"{MC_1D_CSV}")
    mc_2d = compute_mc_block(_load_rows(MC_2D_CSV),
                             "mc_2d",
                             "results_2d/summary.csv (via run_monte_carlo_2d.py -n 200 -t 40000 -w 16)")
    abl   = compute_ablations_block()

    # preserve hand-written fields that the auto-compute can't reproduce
    preserved = {
        "manuscript_sentence": existing.get("mc_1d", {}).get("manuscript_sentence"),
        "engine_parameters":   existing.get("engine_parameters"),
        "figures":             existing.get("figures"),
        "pilot_2d":            existing.get("pilot_2d"),
    }

    mc_1d["manuscript_sentence"] = preserved["manuscript_sentence"]

    out = {
        "schema_version": "1.0",
        "last_updated":   __import__("datetime").date.today().isoformat(),
        "notes":          existing.get("notes",
                          "Canonical aggregate statistics for the manuscript."),
        "mc_1d":             mc_1d,
        "ablations":         abl,
        "pilot_2d":          preserved["pilot_2d"],
        "mc_2d":             mc_2d,
        "engine_parameters": preserved["engine_parameters"],
        "figures":           preserved["figures"],
    }
    OUT_JSON.write_text(json.dumps(out, indent=2))
    print(f"wrote {OUT_JSON}  ({OUT_JSON.stat().st_size} bytes)")
    print(f"  mc_1d:     n={mc_1d.get('n_runs')}  cbm={mc_1d.get('clock_before_map', {}).get('cbm_count')}")
    print(f"  mc_2d:     n={mc_2d.get('n_runs', 'pending')}")
    print(f"  ablations: conditions={abl.get('totals', {}).get('total_conditions')}")


if __name__ == "__main__":
    main()
