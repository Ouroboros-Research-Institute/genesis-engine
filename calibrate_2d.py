"""
calibrate_2d.py — Empirical calibration of Da/Db rescale factor for the 2D lift.

Instead of hunting Turing spots (which neither 1D nor 2D actually form at
in-range genomes), we match the *statistical character* of the RD field
between the 1D ring and the 2D sphere. The four statistics that `pattern_s`
actually depends on:

    - mean_v     (typical amplitude)
    - std_v      (spatial variance)
    - max_v      (peak amplitude)
    - autocorr(τ=50 ticks)   (temporal persistence)

Protocol
--------
For each candidate rescale factor α ∈ {0.033, 0.068, 0.15, 0.30, 1.0}:
    - Sample 8 genomes from the 1D genome range (fixed seed for reproducibility).
    - For each genome:
        * Run 1D RD for 3000 ticks, record v-field every 10 ticks.
        * Run 2D RD with (Da·α, Db·α, f, k) for 3000 ticks, record v every 10 ticks.
        * Compute (mean, std, max, autocorr(50)) on each.
    - Average stats across genomes.
    - Compute normalized distance:
        d(α) = Σ_stat |log(stat_2d / stat_1d)|
      (log so that 1×/2× and 2×/1× penalize equally; sum over 4 stats).
    - Pick α* = argmin d(α).

No growth perturbation, no division — just the pure RD dynamics driven by
stochastic noise. The growth/division coupling is the same code path in 1D
and 2D so it can be calibrated separately in Stage 3.
"""

from __future__ import annotations
import numpy as np
from scipy.sparse import diags
from dataclasses import dataclass

# 1D imports (do NOT modify genesis_engine)
from genesis_engine import rd_step, Cell, Genome, N_NODES, RD_STEPS as RD_STEPS_1D

# 2D imports
from mesh_utils import icosphere, cotangent_weights
from genesis_engine_2d import rd_step_2d, Genome2D, RD_STEPS as RD_STEPS_2D


# ─────────────────────────── harness constants ─────────────────────────
N_GENOMES   = 8
TICKS       = 2000       # shorter — RD_STEPS=90 makes 2D expensive
SAMPLE_EVERY = 10
AUTOCORR_LAG = 50   # ticks → 50/SAMPLE_EVERY = 5 snapshot-steps
# Fine sweep around the transition region found in the first pass
CANDIDATES  = [0.33, 0.35, 0.37, 0.40, 0.43, 0.47]


def sample_genomes(n: int, rng: np.random.Generator) -> list[dict]:
    """Sample n genomes from the 1D bounds."""
    out = []
    for _ in range(n):
        out.append({
            "Da": float(rng.uniform(0.02, 0.12)),
            "Db": float(rng.uniform(0.15, 0.60)),
            "f":  float(rng.uniform(0.01, 0.08)),
            "k":  float(rng.uniform(0.03, 0.08)),
        })
    return out


# ─────────────────────────── 1D run ──────────────────────────────────
def run_1d(genome: dict, seed: int) -> np.ndarray:
    """Run 1D RD for TICKS ticks, return (n_snapshots, N_NODES) v-field stack."""
    rng = np.random.default_rng(seed)
    u = np.ones(N_NODES) + rng.normal(0, 0.05, N_NODES)
    v = np.abs(rng.normal(0, 0.02, N_NODES))
    si = rng.integers(0, N_NODES)
    v[si] = 0.5
    v[(si + 1) % N_NODES] = 0.25
    cell = Cell(
        genome=Genome(**genome),
        u=u.copy(),
        v=v.copy(),
    )
    snaps = []
    for t in range(TICKS):
        for _ in range(RD_STEPS_1D):
            rd_step(cell, rng)
        if t % SAMPLE_EVERY == 0:
            snaps.append(cell.v.copy())
    return np.asarray(snaps)


# ─────────────────────────── 2D run ──────────────────────────────────
def run_2d(genome: dict, alpha: float, Delta, verts, N: int, seed: int) -> np.ndarray:
    """Run 2D RD with rescaled Da,Db for TICKS ticks."""
    rng = np.random.default_rng(seed)
    u = np.ones(N) + rng.normal(0, 0.05, N)
    v = np.abs(rng.normal(0, 0.02, N))
    # 1D seeds 2 points with v=0.5, 0.25. On sphere do the same: pick a
    # random vertex and its first neighbor.
    from genesis_engine_2d import face_adjacency  # reuse
    # simpler: pick two random vertices
    si = int(rng.integers(0, N))
    # pick a nearest neighbor (vertex with max dot product with si, excluding itself)
    dots = verts @ verts[si]
    dots[si] = -np.inf
    sj = int(np.argmax(dots))
    v[si] = 0.5
    v[sj] = 0.25

    g2d = Genome2D(
        Da=genome["Da"] * alpha,
        Db=genome["Db"] * alpha,
        f=genome["f"],
        k=genome["k"],
    )
    snaps = []
    for t in range(TICKS):
        u, v = rd_step_2d(u, v, Delta, g2d, rng)
        if t % SAMPLE_EVERY == 0:
            snaps.append(v.copy())
    return np.asarray(snaps)


# ─────────────────────────── statistics ──────────────────────────────
def stat_bundle(snaps: np.ndarray, lag_steps: int) -> dict:
    """Compute summary stats on a (T, N) v-field stack."""
    # discard first 1/3 as transient
    burn = snaps.shape[0] // 3
    s = snaps[burn:]
    mean_v = float(s.mean())
    std_v  = float(s.std())
    max_v  = float(s.max())
    # temporal autocorr at lag
    if s.shape[0] <= lag_steps + 1:
        autocorr = 0.0
    else:
        a = s[:-lag_steps].reshape(s.shape[0] - lag_steps, -1)
        b = s[lag_steps:].reshape(s.shape[0] - lag_steps, -1)
        # per-snapshot-pair Pearson correlation, then average
        corrs = []
        for x, y in zip(a, b):
            x = x - x.mean()
            y = y - y.mean()
            denom = np.sqrt((x * x).sum() * (y * y).sum())
            if denom > 1e-10:
                corrs.append(float((x * y).sum() / denom))
        autocorr = float(np.mean(corrs)) if corrs else 0.0
    return {"mean_v": mean_v, "std_v": std_v, "max_v": max_v, "autocorr": autocorr}


def log_distance(s1: dict, s2: dict) -> float:
    """Sum of |log(s2/s1)| over non-autocorr stats; for autocorr use abs diff."""
    d = 0.0
    for key in ("mean_v", "std_v", "max_v"):
        a, b = s1[key], s2[key]
        eps = 1e-6
        d += abs(np.log((b + eps) / (a + eps)))
    # autocorr is in [-1, 1] — use absolute difference (not log)
    d += abs(s1["autocorr"] - s2["autocorr"])
    return d


# ─────────────────────────── main ──────────────────────────────────
def _main():
    print("=" * 78)
    print("calibrate_2d.py — 1D↔2D rescale factor sweep")
    print("=" * 78)

    rng_master = np.random.default_rng(2026)
    genomes = sample_genomes(N_GENOMES, rng_master)
    print(f"{N_GENOMES} genomes sampled from 1D range, {TICKS} ticks each\n")

    # Build mesh once (reused across all runs)
    verts, faces = icosphere(3)
    L, M = cotangent_weights(verts, faces)
    Delta = (diags(1.0 / M) @ L).tocsr()
    N = len(verts)
    print(f"sphere: {N} verts  |  RD_STEPS_1D={RD_STEPS_1D}  RD_STEPS_2D={RD_STEPS_2D}\n")

    lag_snap_steps = AUTOCORR_LAG // SAMPLE_EVERY

    # Run 1D baselines
    print("Running 1D baselines…", end=" ", flush=True)
    stats_1d = []
    for i, g in enumerate(genomes):
        snaps = run_1d(g, seed=1000 + i)
        stats_1d.append(stat_bundle(snaps, lag_snap_steps))
    print("done")
    mean_1d = {k: float(np.mean([s[k] for s in stats_1d])) for k in stats_1d[0]}
    print(f"  1D avg stats: {mean_1d}\n")

    # Sweep candidates
    print(f"{'alpha':>8}  {'mean_v 2d':>11}  {'std_v':>9}  {'max_v':>9}  "
          f"{'autocorr':>9}  {'Δ vs 1D':>9}")
    print("-" * 78)

    results = {}
    for alpha in CANDIDATES:
        stats_2d = []
        for i, g in enumerate(genomes):
            snaps = run_2d(g, alpha, Delta, verts, N, seed=1000 + i)
            stats_2d.append(stat_bundle(snaps, lag_snap_steps))
        mean_2d = {k: float(np.mean([s[k] for s in stats_2d])) for k in stats_2d[0]}
        d = log_distance(mean_1d, mean_2d)
        results[alpha] = (mean_2d, d)
        print(f"  {alpha:>6.3f}  {mean_2d['mean_v']:>11.5f}  {mean_2d['std_v']:>9.5f}  "
              f"{mean_2d['max_v']:>9.5f}  {mean_2d['autocorr']:>9.4f}  {d:>9.4f}")

    # Pick winner
    alpha_star = min(results, key=lambda a: results[a][1])
    print("-" * 78)
    print(f"  1D REF  {mean_1d['mean_v']:>11.5f}  {mean_1d['std_v']:>9.5f}  "
          f"{mean_1d['max_v']:>9.5f}  {mean_1d['autocorr']:>9.4f}       —")
    print()
    print(f"WINNER: α* = {alpha_star:.3f}   (d = {results[alpha_star][1]:.4f})")

    # Print rescaled bounds for the winner
    print()
    print("Rescaled genome bounds at α*:")
    print(f"  Da ∈ [{0.02*alpha_star:.5f}, {0.12*alpha_star:.5f}]   "
          f"(1D: [0.02, 0.12])")
    print(f"  Db ∈ [{0.15*alpha_star:.5f}, {0.60*alpha_star:.5f}]   "
          f"(1D: [0.15, 0.60])")
    print(f"  f, k unchanged (dimensionless)")
    return alpha_star


if __name__ == "__main__":
    _main()
