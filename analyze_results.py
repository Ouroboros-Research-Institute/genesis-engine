"""
Genesis Engine — Statistical Analysis
Reads Monte Carlo results, computes statistics, generates figures.
"""

import csv
import os
import argparse
import numpy as np

def load_summary(path):
    """Load summary.csv into list of dicts."""
    rows = []
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            row["seed"] = int(row["seed"])
            row["phase_B_tick"] = int(row["phase_B_tick"])
            row["phase_C_tick"] = int(row["phase_C_tick"])
            row["phase_D_tick"] = int(row["phase_D_tick"])
            row["final_pop"] = int(row["final_pop"])
            row["final_mean_s"] = float(row["final_mean_s"])
            row["final_mean_cv"] = float(row["final_mean_cv"])
            row["final_max_gen"] = int(row["final_max_gen"])
            row["total_divisions"] = int(row["total_divisions"])
            row["clock_before_map"] = row["clock_before_map"] == "True"
            rows.append(row)
    return rows


def load_timeseries(ts_dir, seed):
    """Load a single run's time series."""
    path = os.path.join(ts_dir, f"run_{seed:04d}.csv")
    ticks, pop, s, cv, res = [], [], [], [], []
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            ticks.append(int(row["tick"]))
            pop.append(int(row["population"]))
            s.append(float(row["mean_s"]))
            cv.append(float(row["mean_cv"]))
            res.append(float(row["resource"]))
    return np.array(ticks), np.array(pop), np.array(s), np.array(cv), np.array(res)


def hedges_g(group1, group2):
    """Compute Hedges' g effect size."""
    n1, n2 = len(group1), len(group2)
    m1, m2 = np.mean(group1), np.mean(group2)
    s1, s2 = np.var(group1, ddof=1), np.var(group2, ddof=1)
    sp = np.sqrt(((n1 - 1) * s1 + (n2 - 1) * s2) / (n1 + n2 - 2))
    if sp == 0:
        return 0.0
    g = (m1 - m2) / sp
    # Correction factor
    cf = 1 - 3 / (4 * (n1 + n2) - 9)
    return g * cf


def main():
    parser = argparse.ArgumentParser(description="Analyze Genesis Engine results")
    parser.add_argument("-d", "--results-dir", type=str, default="results")
    parser.add_argument("--plot", action="store_true", help="Generate matplotlib figures")
    args = parser.parse_args()

    summary_path = os.path.join(args.results_dir, "summary.csv")
    ts_dir = os.path.join(args.results_dir, "timeseries")

    if not os.path.exists(summary_path):
        print(f"No summary.csv found in {args.results_dir}/")
        return

    data = load_summary(summary_path)
    n = len(data)
    print(f"Loaded {n} runs from {summary_path}")

    # ─── Phase transition analysis ────────────────────────────────
    b_ticks = np.array([r["phase_B_tick"] for r in data if r["phase_B_tick"] > 0])
    c_ticks = np.array([r["phase_C_tick"] for r in data if r["phase_C_tick"] > 0])
    d_ticks = np.array([r["phase_D_tick"] for r in data if r["phase_D_tick"] > 0])

    reached_b = len(b_ticks)
    reached_c = len(c_ticks)
    reached_d = len(d_ticks)

    print(f"\n{'='*70}")
    print(f"PHASE TRANSITION ANALYSIS (N={n})")
    print(f"{'='*70}")

    phases = [r["final_phase"] for r in data]
    for p in ["A", "B", "C", "D"]:
        count = phases.count(p)
        print(f"  Final phase {p}: {count:4d} ({100*count/n:.1f}%)")

    print(f"\n  Reached Clock (B):  {reached_b:4d}/{n} ({100*reached_b/n:.1f}%)")
    print(f"  Reached Map (C):    {reached_c:4d}/{n} ({100*reached_c/n:.1f}%)")
    print(f"  Reached Agency (D): {reached_d:4d}/{n} ({100*reached_d/n:.1f}%)")

    if len(b_ticks) > 1:
        print(f"\n  Clock transition:  {b_ticks.mean():8.0f} ± {b_ticks.std():6.0f} ticks "
              f"(95% CI: [{np.percentile(b_ticks, 2.5):.0f}, {np.percentile(b_ticks, 97.5):.0f}])")
    if len(c_ticks) > 1:
        print(f"  Map transition:    {c_ticks.mean():8.0f} ± {c_ticks.std():6.0f} ticks "
              f"(95% CI: [{np.percentile(c_ticks, 2.5):.0f}, {np.percentile(c_ticks, 97.5):.0f}])")
    if len(d_ticks) > 1:
        print(f"  Agency transition: {d_ticks.mean():8.0f} ± {d_ticks.std():6.0f} ticks "
              f"(95% CI: [{np.percentile(d_ticks, 2.5):.0f}, {np.percentile(d_ticks, 97.5):.0f}])")

    # ─── KEY HYPOTHESIS: Clock before Map ─────────────────────────
    print(f"\n{'='*70}")
    print(f"KEY HYPOTHESIS: Clock → Map ordering is mandatory")
    print(f"{'='*70}")

    both = [(r["phase_B_tick"], r["phase_C_tick"]) for r in data
            if r["phase_B_tick"] > 0 and r["phase_C_tick"] > 0]
    if both:
        b_before_c = sum(1 for b, c in both if b < c)
        c_before_b = sum(1 for b, c in both if c < b)
        simultaneous = sum(1 for b, c in both if b == c)

        print(f"  Runs reaching both B and C: {len(both)}")
        print(f"  Clock before Map (B < C):   {b_before_c} ({100*b_before_c/len(both):.1f}%)")
        print(f"  Map before Clock (C < B):   {c_before_b} ({100*c_before_b/len(both):.1f}%)")
        print(f"  Simultaneous:               {simultaneous}")

        if len(both) > 0:
            from scipy import stats as sp
            # Binomial test: H0 = random ordering (p=0.5)
            p_binom = sp.binomtest(b_before_c, b_before_c + c_before_b, 0.5, alternative="greater").pvalue
            print(f"\n  Binomial test (H0: random ordering): p = {p_binom:.2e}")

            # Wilcoxon signed-rank on transition time differences
            diffs = np.array([c - b for b, c in both])
            if len(diffs) > 10:
                stat, p_wilcox = sp.wilcoxon(diffs, alternative="greater")
                print(f"  Wilcoxon signed-rank (H0: no delay): W={stat:.0f}, p = {p_wilcox:.2e}")
                print(f"  Mean delay (C - B): {diffs.mean():.0f} ± {diffs.std():.0f} ticks")

            if b_before_c == len(both):
                print(f"\n  >>> CLOCK PRECEDED MAP IN 100% OF RUNS (N={len(both)}) <<<")

    # ─── Effect size: organized vs unorganized ────────────────────
    print(f"\n{'='*70}")
    print(f"THERMODYNAMIC SELECTION (Engine)")
    print(f"{'='*70}")

    organized = [r["final_pop"] for r in data if r["final_mean_s"] > 0.3]
    disorganized = [r["final_pop"] for r in data if r["final_mean_s"] < 0.1]

    if organized and disorganized:
        g = hedges_g(np.array(organized), np.array(disorganized))
        print(f"  Organized runs (S > 0.3):   N={len(organized)}, mean pop={np.mean(organized):.1f}")
        print(f"  Disorganized (S < 0.1):     N={len(disorganized)}, mean pop={np.mean(disorganized):.1f}")
        print(f"  Hedges' g (effect size):    {g:.2f}")
        if abs(g) > 0.8:
            print(f"  >> Large effect size (|g| > 0.8)")

    # ─── Final state statistics ───────────────────────────────────
    print(f"\n{'='*70}")
    print(f"FINAL STATE STATISTICS")
    print(f"{'='*70}")

    final_s = np.array([r["final_mean_s"] for r in data])
    final_cv = np.array([r["final_mean_cv"] for r in data if r["final_mean_cv"] < 1.0])
    final_pop = np.array([r["final_pop"] for r in data])
    final_gen = np.array([r["final_max_gen"] for r in data])

    print(f"  Pattern S:  {final_s.mean():.3f} ± {final_s.std():.3f}")
    print(f"  Division CV: {final_cv.mean():.3f} ± {final_cv.std():.3f}" if len(final_cv) > 0 else "  Division CV: N/A")
    print(f"  Population: {final_pop.mean():.1f} ± {final_pop.std():.1f}")
    print(f"  Max gen:    {final_gen.mean():.1f} ± {final_gen.std():.1f}")

    # ─── Plots ────────────────────────────────────────────────────
    if args.plot:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            fig_dir = os.path.join(args.results_dir, "figures")
            os.makedirs(fig_dir, exist_ok=True)

            # Fig 1: Phase transition times
            fig, ax = plt.subplots(1, 1, figsize=(10, 6))
            if len(b_ticks) > 0:
                ax.hist(b_ticks, bins=30, alpha=0.7, label=f"B (Clock) N={len(b_ticks)}", color="#ffcc40")
            if len(c_ticks) > 0:
                ax.hist(c_ticks, bins=30, alpha=0.7, label=f"C (Map) N={len(c_ticks)}", color="#80ff80")
            if len(d_ticks) > 0:
                ax.hist(d_ticks, bins=30, alpha=0.7, label=f"D (Agency) N={len(d_ticks)}", color="#50ddff")
            ax.set_xlabel("Tick")
            ax.set_ylabel("Count")
            ax.set_title("Phase Transition Times (Clock → Map → Engine)")
            ax.legend()
            plt.tight_layout()
            plt.savefig(os.path.join(fig_dir, "phase_transitions.png"), dpi=150)
            print(f"\n  Saved: {fig_dir}/phase_transitions.png")

            # Fig 2: B vs C transition times scatter
            if both:
                fig, ax = plt.subplots(1, 1, figsize=(8, 8))
                bs = [b for b, c in both]
                cs = [c for b, c in both]
                ax.scatter(bs, cs, alpha=0.5, s=20, c="#50ddff")
                lim = max(max(bs), max(cs)) * 1.1
                ax.plot([0, lim], [0, lim], "r--", alpha=0.5, label="B = C (simultaneous)")
                ax.set_xlabel("Clock transition (B) tick")
                ax.set_ylabel("Map transition (C) tick")
                ax.set_title("Clock vs Map Transition: Points above line = Clock first")
                ax.legend()
                plt.tight_layout()
                plt.savefig(os.path.join(fig_dir, "clock_vs_map.png"), dpi=150)
                print(f"  Saved: {fig_dir}/clock_vs_map.png")

            # Fig 3: Example time series (first 5 runs that reached D)
            d_runs = [r for r in data if r["final_phase"] == "D"][:5]
            if d_runs and os.path.exists(ts_dir):
                fig, axes = plt.subplots(4, 1, figsize=(12, 10), sharex=True)
                for r in d_runs:
                    t, pop, s, cv, res = load_timeseries(ts_dir, r["seed"])
                    axes[0].plot(t, pop, alpha=0.6, linewidth=0.8)
                    axes[1].plot(t, s, alpha=0.6, linewidth=0.8)
                    axes[2].plot(t, cv, alpha=0.6, linewidth=0.8)
                    axes[3].plot(t, res, alpha=0.6, linewidth=0.8)
                    # Mark phase transitions
                    for ax in axes:
                        if r["phase_B_tick"] > 0:
                            ax.axvline(r["phase_B_tick"], color="#ffcc40", alpha=0.3, linestyle="--")
                        if r["phase_C_tick"] > 0:
                            ax.axvline(r["phase_C_tick"], color="#80ff80", alpha=0.3, linestyle="--")
                        if r["phase_D_tick"] > 0:
                            ax.axvline(r["phase_D_tick"], color="#50ddff", alpha=0.3, linestyle="--")

                axes[0].set_ylabel("Population")
                axes[1].set_ylabel("Pattern S")
                axes[2].set_ylabel("Division CV")
                axes[3].set_ylabel("Resources")
                axes[3].set_xlabel("Tick")
                axes[0].set_title("Example Runs Reaching Agency (D) — vertical lines = phase transitions")
                plt.tight_layout()
                plt.savefig(os.path.join(fig_dir, "example_timeseries.png"), dpi=150)
                print(f"  Saved: {fig_dir}/example_timeseries.png")

            plt.close("all")

        except ImportError:
            print("\n  matplotlib not available — skipping plots")
            print("  Install: pip install matplotlib")

    print(f"\nAnalysis complete.")


if __name__ == "__main__":
    main()
