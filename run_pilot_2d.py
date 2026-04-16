"""
run_pilot_2d.py — N=10 pilot of the 2D sphere simulation.

Confirms Stage 3 seed=42 wasn't a lucky run.  Ten independent seeds,
10 000 ticks each, 8 workers.  Reports phase distribution, B/C tick
stats, and — the headline — the Clock→Map ordering rate.

Intended as a PASS/FAIL gate before committing to N=200 overnight.
"""

from __future__ import annotations
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Optional

from genesis_engine_2d import run_simulation, SimResult


def _worker(seed: int) -> SimResult:
    return run_simulation(seed=seed, max_ticks=10_000, verbose=False)


def main():
    N = 10
    ticks = 10_000
    workers = 8
    seeds = list(range(N))

    print("=" * 68)
    print(f"2D sphere pilot:  N={N}  ticks={ticks}  workers={workers}")
    print("=" * 68)

    t0 = time.time()
    results: list[SimResult] = []
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(_worker, s): s for s in seeds}
        for f in as_completed(futures):
            r = f.result()
            results.append(r)
            elapsed = time.time() - t0
            print(f"  seed={r.seed:2d}  phase={r.final_phase}  "
                  f"B={r.phase_B_tick:>5d}  C={r.phase_C_tick:>5d}  "
                  f"D={r.phase_D_tick:>5d}  pop={r.final_pop:>3d}  "
                  f"S={r.final_mean_s:.3f}  CBM={r.clock_before_map}  "
                  f"[{elapsed:.0f}s]")

    results.sort(key=lambda r: r.seed)
    elapsed = time.time() - t0
    print()
    print(f"Total runtime: {elapsed:.1f} s")
    print()

    # ---- summary ----
    phase_count = {p: sum(1 for r in results if r.final_phase == p)
                   for p in "ABCD"}
    reached_B = sum(1 for r in results if r.phase_B_tick > 0)
    reached_C = sum(1 for r in results if r.phase_C_tick > 0)
    reached_D = sum(1 for r in results if r.phase_D_tick > 0)
    both_BC   = [r for r in results if r.phase_B_tick > 0 and r.phase_C_tick > 0]
    cbm_true  = sum(1 for r in both_BC if r.clock_before_map)
    cbm_false = sum(1 for r in both_BC if r.clock_before_map is False)
    violations = sum(1 for r in both_BC if r.phase_B_tick >= r.phase_C_tick)

    print("Phase distribution:")
    for p in "ABCD":
        print(f"  {p}: {phase_count[p]}/{N}")

    print()
    print(f"Reached Clock (B): {reached_B}/{N}  "
          f"({100*reached_B/N:.0f}%)")
    print(f"Reached Map   (C): {reached_C}/{N}  "
          f"({100*reached_C/N:.0f}%)")
    print(f"Reached Agency(D): {reached_D}/{N}  "
          f"({100*reached_D/N:.0f}%)")

    if both_BC:
        import statistics as st
        B_vals = [r.phase_B_tick for r in both_BC]
        C_vals = [r.phase_C_tick for r in both_BC]
        delays = [C - B for B, C in zip(B_vals, C_vals)]
        print()
        print(f"Among {len(both_BC)} runs reaching both B and C:")
        print(f"  B_tick:  mean={st.mean(B_vals):.0f}  "
              f"median={st.median(B_vals):.0f}  min={min(B_vals)}  max={max(B_vals)}")
        print(f"  C_tick:  mean={st.mean(C_vals):.0f}  "
              f"median={st.median(C_vals):.0f}  min={min(C_vals)}  max={max(C_vals)}")
        print(f"  C - B:   mean={st.mean(delays):.0f}  "
              f"median={st.median(delays):.0f}  min={min(delays)}  max={max(delays)}")

    print()
    print("*** Clock→Map ordering ***")
    print(f"  Clock before Map (B < C): {cbm_true}/{len(both_BC)}")
    print(f"  Map before Clock (C < B): {cbm_false}/{len(both_BC)}")
    print(f"  Ordering violations:      {violations}/{len(both_BC)}")
    print()

    passed = violations == 0 and reached_B >= N * 0.8
    print("=" * 68)
    print("2D PILOT:", "PASS ✓" if passed else "FAIL ✗")
    print("=" * 68)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
