"""
Genesis Engine — Parameter Sensitivity Ablations

For each of 4 parameters, run N simulations at low / baseline / high values
and measure whether the Clock → Map ordering holds.

12 conditions × 100 runs × 40k ticks by default.

Output: results/ablations/ablation_summary.csv + per-condition time-series CSVs.
"""

import csv
import time
import argparse
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from genesis_engine import run_simulation, SimResult

# Baseline values (must match genesis_engine.py)
BASELINES = {
    "LIPID_SUPPLY":   0.015,
    "RD_NOISE":       0.004,
    "GROWTH_PERTURB": 0.15,
    "STAB_WINDOW":    40,
}

# Sweeps: (parameter, [low, baseline, high])
SWEEPS = [
    ("LIPID_SUPPLY",   [0.008, 0.015, 0.025]),
    ("RD_NOISE",       [0.001, 0.004, 0.010]),
    ("GROWTH_PERTURB", [0.05,  0.15,  0.30]),
    ("STAB_WINDOW",    [20,    40,    80]),
]


def run_one(args):
    """Parallel worker: run a single simulation with overrides."""
    seed, max_ticks, overrides = args
    r = run_simulation(seed=seed, max_ticks=max_ticks, overrides=overrides)
    return r


def _safe_mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else float("nan")


def run_condition(param, value, n_runs, max_ticks, workers):
    """Run N simulations for a single (parameter, value) condition."""
    overrides = {param: value}
    tasks = [(seed, max_ticks, overrides) for seed in range(n_runs)]
    results = []
    t0 = time.time()

    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(run_one, task): task[0] for task in tasks}
        for future in as_completed(futures):
            results.append(future.result())

    elapsed = time.time() - t0
    results.sort(key=lambda r: r.seed)

    # aggregate stats
    both      = [r for r in results if r.phase_B_tick > 0 and r.phase_C_tick > 0]
    reached_b = [r for r in results if r.phase_B_tick > 0]
    reached_c = [r for r in results if r.phase_C_tick > 0]
    reached_d = [r for r in results if r.phase_D_tick > 0]

    cbm_true = sum(1 for r in both if r.phase_B_tick < r.phase_C_tick)
    delays   = [r.phase_C_tick - r.phase_B_tick for r in both]

    phase_dist = {p: sum(1 for r in results if r.final_phase == p) for p in "ABCD"}

    summary = {
        "parameter":            param,
        "value":                value,
        "is_baseline":          value == BASELINES[param],
        "n_runs":               n_runs,
        "n_reached_B":          len(reached_b),
        "n_reached_C":          len(reached_c),
        "n_reached_D":          len(reached_d),
        "n_reached_both":       len(both),
        "clock_before_map_count": cbm_true,
        "clock_before_map_pct": 100.0 * cbm_true / len(both) if both else float("nan"),
        "mean_B_tick":          _safe_mean([r.phase_B_tick for r in reached_b]),
        "mean_C_tick":          _safe_mean([r.phase_C_tick for r in reached_c]),
        "mean_D_tick":          _safe_mean([r.phase_D_tick for r in reached_d]),
        "mean_delay":           _safe_mean(delays),
        "mean_final_S":         _safe_mean([r.final_mean_s for r in results]),
        "mean_final_CV":        _safe_mean([r.final_mean_cv for r in results]),
        "mean_final_pop":       _safe_mean([r.final_pop for r in results]),
        "mean_max_gen":         _safe_mean([r.final_max_gen for r in results]),
        "phase_A":              phase_dist["A"],
        "phase_B":              phase_dist["B"],
        "phase_C":              phase_dist["C"],
        "phase_D":              phase_dist["D"],
        "elapsed_s":            round(elapsed, 1),
    }
    return summary, results


def main():
    p = argparse.ArgumentParser(description="Genesis Engine — Parameter Ablations")
    p.add_argument("-n", "--n-runs", type=int, default=100)
    p.add_argument("-t", "--max-ticks", type=int, default=40000)
    p.add_argument("-w", "--workers", type=int, default=16)
    p.add_argument("-o", "--output-dir", type=str, default="results/ablations")
    args = p.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    os.makedirs(os.path.join(args.output_dir, "per_run"), exist_ok=True)

    conditions = [(param, v) for param, vs in SWEEPS for v in vs]
    total_runs = len(conditions) * args.n_runs

    print(f"Genesis Engine — Parameter Ablation Study")
    print(f"  Conditions: {len(conditions)} ({len(SWEEPS)} params × 3 values)")
    print(f"  Runs per condition: {args.n_runs}")
    print(f"  Max ticks: {args.max_ticks}")
    print(f"  Workers: {args.workers}")
    print(f"  Total runs: {total_runs}")
    print(f"  Output: {args.output_dir}/")
    print()

    summary_path = os.path.join(args.output_dir, "ablation_summary.csv")
    fieldnames = [
        "parameter", "value", "is_baseline", "n_runs",
        "n_reached_B", "n_reached_C", "n_reached_D", "n_reached_both",
        "clock_before_map_count", "clock_before_map_pct",
        "mean_B_tick", "mean_C_tick", "mean_D_tick", "mean_delay",
        "mean_final_S", "mean_final_CV", "mean_final_pop", "mean_max_gen",
        "phase_A", "phase_B", "phase_C", "phase_D",
        "elapsed_s",
    ]

    # write header up front; append after each condition for live progress
    with open(summary_path, "w", newline="") as f:
        csv.DictWriter(f, fieldnames=fieldnames).writeheader()

    t_all = time.time()
    all_summaries = []

    for i, (param, value) in enumerate(conditions):
        marker = " (baseline)" if value == BASELINES[param] else ""
        print(f"[{i+1:2d}/{len(conditions)}] {param} = {value}{marker}  ...  ", end="", flush=True)

        summary, results = run_condition(
            param, value, args.n_runs, args.max_ticks, args.workers
        )
        all_summaries.append(summary)

        # append this row to the summary CSV
        with open(summary_path, "a", newline="") as f:
            csv.DictWriter(f, fieldnames=fieldnames).writerow(summary)

        # per-condition per-run detail
        tag = f"{param}_{value}".replace(".", "p")
        per_run_path = os.path.join(args.output_dir, "per_run", f"{tag}.csv")
        with open(per_run_path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["seed", "final_phase", "phase_B_tick", "phase_C_tick",
                        "phase_D_tick", "clock_before_map",
                        "final_pop", "final_mean_s", "final_mean_cv",
                        "final_max_gen", "total_divisions"])
            for r in results:
                w.writerow([r.seed, r.final_phase, r.phase_B_tick, r.phase_C_tick,
                            r.phase_D_tick, r.clock_before_map,
                            r.final_pop, f"{r.final_mean_s:.4f}",
                            f"{r.final_mean_cv:.4f}", r.final_max_gen,
                            r.total_divisions])

        n_both = summary["n_reached_both"]
        cbm_pct = summary["clock_before_map_pct"]
        cbm_str = f"{cbm_pct:5.1f}%" if n_both > 0 else "  N/A "
        print(f"Clock→Map: {summary['clock_before_map_count']:3d}/{n_both:3d} ({cbm_str})  "
              f"[{summary['elapsed_s']:6.1f}s]")

    t_total = time.time() - t_all
    print(f"\nTotal elapsed: {t_total:.1f}s ({t_total/60:.1f} min)")

    # ──────────────── pretty results table ────────────────
    print("\n" + "="*78)
    print("ABLATION RESULTS — Clock → Map ordering held across all conditions?")
    print("="*78)
    print(f"{'Parameter':<18} {'Low':>12} {'Baseline':>12} {'High':>12}")
    print("-"*78)
    for param, vs in SWEEPS:
        rows = [s for s in all_summaries if s["parameter"] == param]
        rows.sort(key=lambda r: r["value"])
        cells = []
        for s in rows:
            n_both = s["n_reached_both"]
            pct = s["clock_before_map_pct"]
            star = "*" if s["is_baseline"] else " "
            if n_both > 0:
                cells.append(f"{star}{s['clock_before_map_count']}/{n_both} ({pct:.0f}%)")
            else:
                cells.append(f"{star}N/A")
        print(f"{param:<18} " + " ".join(f"{c:>12}" for c in cells))
    print("-"*78)
    print("(* = baseline value)")

    # overall PASS/FAIL
    any_failed = False
    for s in all_summaries:
        if s["n_reached_both"] > 0 and s["clock_before_map_pct"] < 100.0:
            any_failed = True
            break
    if not any_failed:
        total_cbm = sum(s["clock_before_map_count"] for s in all_summaries)
        total_both = sum(s["n_reached_both"] for s in all_summaries)
        print(f"\n>>> CLOCK → MAP ORDERING HELD IN {total_cbm}/{total_both} RUNS "
              f"({100.0*total_cbm/total_both:.1f}%) ACROSS ALL 12 CONDITIONS <<<")
    else:
        print(f"\n>>> SOME CONDITIONS SHOWED VIOLATIONS — see ablation_summary.csv <<<")


if __name__ == "__main__":
    main()
