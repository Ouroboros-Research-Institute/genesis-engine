"""
Genesis Engine — Monte Carlo Runner
Runs N independent simulations in parallel, logs results to CSV.
"""

import csv
import time
import argparse
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from genesis_engine import run_simulation, SimResult

DEFAULT_N_RUNS = 500
DEFAULT_MAX_TICKS = 80000
DEFAULT_WORKERS = 8  # Mac Studio M1 Ultra has plenty of cores


def run_one(args):
    """Wrapper for parallel execution."""
    seed, max_ticks = args
    return run_simulation(seed=seed, max_ticks=max_ticks, verbose=False)


def main():
    parser = argparse.ArgumentParser(description="Genesis Engine Monte Carlo")
    parser.add_argument("-n", "--n-runs", type=int, default=DEFAULT_N_RUNS, help="Number of runs")
    parser.add_argument("-t", "--max-ticks", type=int, default=DEFAULT_MAX_TICKS, help="Max ticks per run")
    parser.add_argument("-w", "--workers", type=int, default=DEFAULT_WORKERS, help="Parallel workers")
    parser.add_argument("-o", "--output-dir", type=str, default="results", help="Output directory")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    print(f"Genesis Engine Monte Carlo")
    print(f"  Runs: {args.n_runs}")
    print(f"  Max ticks: {args.max_ticks}")
    print(f"  Workers: {args.workers}")
    print(f"  Output: {args.output_dir}/")
    print()

    # ─── Run simulations ──────────────────────────────────────────
    tasks = [(seed, args.max_ticks) for seed in range(args.n_runs)]
    results: list[SimResult] = []

    t0 = time.time()
    completed = 0

    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_one, task): task[0] for task in tasks}
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            completed += 1
            if completed % 10 == 0 or completed == args.n_runs:
                elapsed = time.time() - t0
                rate = completed / elapsed
                eta = (args.n_runs - completed) / rate if rate > 0 else 0
                print(f"  [{completed:4d}/{args.n_runs}] {rate:.1f} runs/s | ETA {eta:.0f}s | last: seed={result.seed} phase={result.final_phase}")

    elapsed = time.time() - t0
    print(f"\nCompleted {args.n_runs} runs in {elapsed:.1f}s ({args.n_runs/elapsed:.1f} runs/s)")

    # Sort by seed
    results.sort(key=lambda r: r.seed)

    # ─── Write summary CSV ────────────────────────────────────────
    summary_path = os.path.join(args.output_dir, "summary.csv")
    with open(summary_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "seed", "max_ticks", "final_phase",
            "phase_B_tick", "phase_C_tick", "phase_D_tick",
            "clock_before_map",
            "final_pop", "final_mean_s", "final_mean_cv",
            "final_max_gen", "total_divisions",
        ])
        for r in results:
            writer.writerow([
                r.seed, r.max_ticks, r.final_phase,
                r.phase_B_tick, r.phase_C_tick, r.phase_D_tick,
                r.clock_before_map,
                r.final_pop, f"{r.final_mean_s:.4f}", f"{r.final_mean_cv:.4f}",
                r.final_max_gen, r.total_divisions,
            ])
    print(f"Summary: {summary_path}")

    # ─── Write time series CSV (one file per run) ─────────────────
    ts_dir = os.path.join(args.output_dir, "timeseries")
    os.makedirs(ts_dir, exist_ok=True)
    for r in results:
        ts_path = os.path.join(ts_dir, f"run_{r.seed:04d}.csv")
        with open(ts_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["tick", "population", "mean_s", "mean_cv", "resource"])
            for i in range(len(r.ts_ticks)):
                writer.writerow([
                    r.ts_ticks[i], r.ts_pop[i],
                    f"{r.ts_mean_s[i]:.4f}", f"{r.ts_mean_cv[i]:.4f}",
                    f"{r.ts_resource[i]:.2f}",
                ])
    print(f"Time series: {ts_dir}/ ({len(results)} files)")

    # ─── Quick stats ──────────────────────────────────────────────
    phases = [r.final_phase for r in results]
    n_a = phases.count("A")
    n_b = phases.count("B")
    n_c = phases.count("C")
    n_d = phases.count("D")

    cbm = [r.clock_before_map for r in results if r.clock_before_map is not None]
    cbm_true = sum(1 for x in cbm if x)
    cbm_total = len(cbm)

    b_ticks = [r.phase_B_tick for r in results if r.phase_B_tick > 0]
    c_ticks = [r.phase_C_tick for r in results if r.phase_C_tick > 0]
    d_ticks = [r.phase_D_tick for r in results if r.phase_D_tick > 0]

    print(f"\n{'='*60}")
    print(f"RESULTS SUMMARY ({args.n_runs} runs, {args.max_ticks} ticks each)")
    print(f"{'='*60}")
    print(f"Phase distribution: A={n_a} B={n_b} C={n_c} D={n_d}")
    print(f"Reached B (Clock):  {len(b_ticks)}/{args.n_runs} ({100*len(b_ticks)/args.n_runs:.1f}%)")
    print(f"Reached C (Map):    {len(c_ticks)}/{args.n_runs} ({100*len(c_ticks)/args.n_runs:.1f}%)")
    print(f"Reached D (Agency): {len(d_ticks)}/{args.n_runs} ({100*len(d_ticks)/args.n_runs:.1f}%)")
    print()

    if b_ticks:
        import numpy as np
        bt = np.array(b_ticks)
        print(f"Clock transition (B): mean={bt.mean():.0f} ± {bt.std():.0f} ticks (median={np.median(bt):.0f})")
    if c_ticks:
        import numpy as np
        ct = np.array(c_ticks)
        print(f"Map transition (C):   mean={ct.mean():.0f} ± {ct.std():.0f} ticks (median={np.median(ct):.0f})")
    if d_ticks:
        import numpy as np
        dt = np.array(d_ticks)
        print(f"Agency transition (D): mean={dt.mean():.0f} ± {dt.std():.0f} ticks (median={np.median(dt):.0f})")

    print()
    print(f"*** KEY HYPOTHESIS ***")
    if cbm_total > 0:
        pct_str = f"{100*cbm_true/cbm_total:.1f}%"
    else:
        pct_str = "N/A"
    print(f"Clock before Map: {cbm_true}/{cbm_total} runs ({pct_str})")
    if cbm_total > 0:
        # Binomial test (scipy >= 1.12 uses binomtest)
        from scipy import stats as sp_stats
        p_val = sp_stats.binomtest(cbm_true, cbm_total, 0.5, alternative="greater").pvalue
        print(f"Binomial test (H0: random ordering): p = {p_val:.2e}")
        if cbm_true == cbm_total:
            print(f">>> CLOCK PRECEDED MAP IN 100% OF RUNS <<<")


if __name__ == "__main__":
    main()
