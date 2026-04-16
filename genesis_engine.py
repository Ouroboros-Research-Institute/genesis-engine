"""
Genesis Engine — Core Simulation
Unified Trinity Framework: Clock → Map → Engine
Farina 2025

Replicates the exact physics from the browser prototype (v3):
- Gray-Scott RD on 24-node ring with continuous chemical noise
- Growth perturbation (domain stretching disrupts patterns)
- Pure geometric instability division (Adder mechanism)
- Thermodynamic coupling: pattern stability → metabolic efficiency
- Sequential phase detection: A → B → C → D
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Optional

# ─── Constants (matched to JSX v3) ────────────────────────────────────
N_NODES = 24           # RD nodes around circumference
MIN_RADIUS = 8.0
LIPID_SUPPLY = 0.015   # constant linear growth rate
LIPID_NOISE = 0.003    # stochastic fluctuation
RD_STEPS = 3           # RD substeps per tick
RD_NOISE = 0.004       # continuous chemical noise per RD step
GROWTH_PERTURB = 0.15  # growth-induced pattern disruption
MAX_RESOURCE = 100.0
RESOURCE_REGEN = 0.35
MAX_CELLS = 100
MUTATION_RATE = 0.1

# Metabolism
E_UPTAKE = 0.12
E_EFFICIENCY = 1.0
E_MAINTENANCE = 0.07
EFF_BONUS = 0.7        # S-linked efficiency multiplier
MAINT_BONUS = 0.35     # S-linked maintenance reduction
UPT_BONUS = 0.12       # S-linked uptake bonus
DEATH_TH = -2.0

# Division
CRIT_THRESHOLD_MEAN = 0.16
CRIT_THRESHOLD_NOISE = 0.015

# Stability measurement
STAB_WINDOW = 40       # ticks between snapshots
STAB_DEPTH = 5         # number of historical snapshots

# Phase detection thresholds
PHASE_B_CV = 0.25      # CV must drop below this for Clock
PHASE_C_S = 0.25       # S must exceed this for Map (after B)
PHASE_D_S = 0.35       # S must exceed this for Agency (after C)
PHASE_D_CV = 0.3       # CV must stay below this for Agency
PHASE_D_GEN = 5        # minimum generation depth for Agency


@dataclass
class Genome:
    Da: float    # activator diffusion
    Db: float    # inhibitor diffusion
    f: float     # feed rate
    k: float     # kill rate

    @staticmethod
    def random(rng: np.random.Generator) -> "Genome":
        return Genome(
            Da=rng.uniform(0.02, 0.12),
            Db=rng.uniform(0.15, 0.6),
            f=rng.uniform(0.01, 0.08),
            k=rng.uniform(0.03, 0.08),
        )

    def mutate(self, rng: np.random.Generator) -> "Genome":
        g = Genome(self.Da, self.Db, self.f, self.k)
        for attr in ["Da", "Db", "f", "k"]:
            if rng.random() < MUTATION_RATE:
                val = getattr(g, attr) + rng.normal(0, 0.012)
                setattr(g, attr, np.clip(val, 0.005, 0.8))
        return g


@dataclass
class Cell:
    genome: Genome
    u: np.ndarray              # activator concentrations
    v: np.ndarray              # inhibitor concentrations
    radius: float = MIN_RADIUS
    prev_radius: float = MIN_RADIUS
    energy: float = 2.0
    age: int = 0
    generation: int = 0
    last_div_age: int = 0
    division_times: list = field(default_factory=list)
    pattern_s: float = 0.0
    snapshots: list = field(default_factory=list)
    stab_tick: int = 0

    @staticmethod
    def create(rng: np.random.Generator, genome: Optional[Genome] = None) -> "Cell":
        g = genome or Genome.random(rng)
        u = np.ones(N_NODES) + rng.normal(0, 0.05, N_NODES)
        v = np.abs(rng.normal(0, 0.02, N_NODES))
        si = rng.integers(0, N_NODES)
        v[si] = 0.5
        v[(si + 1) % N_NODES] = 0.25
        return Cell(
            genome=g, u=u, v=v,
            radius=MIN_RADIUS + rng.uniform(0, 2),
            energy=rng.uniform(1, 3),
        )


def rd_step(cell: Cell, rng: np.random.Generator):
    """Gray-Scott reaction-diffusion on ring with continuous noise."""
    u, v = cell.u, cell.v
    Da, Db, f, k = cell.genome.Da, cell.genome.Db, cell.genome.f, cell.genome.k
    n = N_NODES

    u_left = np.roll(u, 1)
    u_right = np.roll(u, -1)
    v_left = np.roll(v, 1)
    v_right = np.roll(v, -1)

    lap_u = u_left + u_right - 2 * u
    lap_v = v_left + v_right - 2 * v
    uvv = u * v * v

    new_u = u + (Da * lap_u - uvv + f * (1.0 - u)) + rng.normal(0, RD_NOISE, n)
    new_v = v + (Db * lap_v + uvv - (f + k) * v) + rng.normal(0, RD_NOISE, n)

    cell.u = np.clip(new_u, 0, 2)
    cell.v = np.clip(new_v, 0, 2)


def apply_growth_perturbation(cell: Cell, growth_frac: float, rng: np.random.Generator):
    """Simulate domain stretching by fractionally shifting pattern."""
    if growth_frac < 0.001:
        return
    shift = growth_frac * GROWTH_PERTURB
    n = N_NODES
    indices = np.arange(n)
    src = (indices + shift) % n
    lo = np.floor(src).astype(int) % n
    hi = (lo + 1) % n
    frac = src - np.floor(src)

    cell.v = cell.v[lo] * (1 - frac) + cell.v[hi] * frac + rng.normal(0, shift * 0.05, n)
    cell.u = cell.u[lo] * (1 - frac) + cell.u[hi] * frac + rng.normal(0, shift * 0.02, n)
    cell.v = np.clip(cell.v, 0, 2)
    cell.u = np.clip(cell.u, 0, 2)


def compute_stability(cell: Cell) -> float:
    """
    Pattern stability via temporal autocorrelation with complexity gate.
    Requires: spatial variance, pattern complexity (multiple peaks),
    and persistence across multiple measurement windows.
    """
    v = cell.v
    n = N_NODES

    # Gate 1: spatial variance
    mean = v.mean()
    variance = np.mean((v - mean) ** 2)
    if variance < 0.002:
        return 0.0

    # Gate 2: complexity — count zero-crossings around mean
    centered = v - mean
    crossings = np.sum(np.diff(np.sign(centered)) != 0)
    complexity_gate = np.clip((crossings - 2) / 4, 0, 1)
    if complexity_gate < 0.1:
        return 0.0

    # Take snapshot
    cell.snapshots.append(v.copy())
    if len(cell.snapshots) > STAB_DEPTH:
        cell.snapshots.pop(0)
    if len(cell.snapshots) < 3:
        return 0.0

    # Temporal autocorrelation across all snapshots
    total_corr = 0.0
    comps = 0
    for hist in cell.snapshots[:-1]:
        h_mean = hist.mean()
        a = v - mean
        b = hist - h_mean
        corr = np.sum(a * b)
        n1 = np.sum(a ** 2)
        n2 = np.sum(b ** 2)
        denom = np.sqrt(n1 * n2)
        if denom > 1e-8:
            total_corr += max(0, corr / denom)
            comps += 1

    if comps == 0:
        return 0.0

    mean_corr = total_corr / comps
    depth_w = (len(cell.snapshots) - 1) / (STAB_DEPTH - 1)
    return float(np.clip(mean_corr * depth_w * complexity_gate, 0, 1))


@dataclass
class PhaseState:
    A: bool = True
    B: bool = False
    C: bool = False
    D: bool = False
    B_tick: int = -1
    C_tick: int = -1
    D_tick: int = -1


def detect_phase(mean_s: float, mean_cv: float, max_gen: int,
                 ph: PhaseState, tick: int) -> str:
    """
    Strict sequential phase detection.
    Each phase requires the previous phase to have been reached in a
    PRIOR measurement cycle (not the same tick). This prevents C from
    piggybacking on B within a single measurement, which would
    invalidate the ordering test.
    """
    if not ph.B and 0 < mean_cv < PHASE_B_CV:
        ph.B = True
        ph.B_tick = tick
    # C requires B to have been set in a PRIOR tick
    if ph.B and ph.B_tick < tick and not ph.C and mean_s > PHASE_C_S:
        ph.C = True
        ph.C_tick = tick
    # D requires C to have been set in a PRIOR tick
    if ph.C and ph.C_tick < tick and not ph.D and max_gen >= PHASE_D_GEN and mean_s > PHASE_D_S and mean_cv < PHASE_D_CV:
        ph.D = True
        ph.D_tick = tick

    if ph.D:
        return "D"
    if ph.C:
        return "C"
    if ph.B:
        return "B"
    return "A"


@dataclass
class SimResult:
    """Results from a single simulation run."""
    seed: int
    max_ticks: int
    phase_B_tick: int = -1
    phase_C_tick: int = -1
    phase_D_tick: int = -1
    final_phase: str = "A"
    final_pop: int = 0
    final_mean_s: float = 0.0
    final_mean_cv: float = 0.0
    final_max_gen: int = 0
    total_divisions: int = 0
    # Time series (sampled every SAMPLE_INTERVAL ticks)
    ts_pop: list = field(default_factory=list)
    ts_mean_s: list = field(default_factory=list)
    ts_mean_cv: list = field(default_factory=list)
    ts_resource: list = field(default_factory=list)
    ts_ticks: list = field(default_factory=list)
    # Was B before C? (the key hypothesis)
    clock_before_map: Optional[bool] = None


SAMPLE_INTERVAL = 50


def run_simulation(seed: int, max_ticks: int = 80000, verbose: bool = False,
                   overrides: Optional[dict] = None) -> SimResult:
    """Run a single simulation to completion or max_ticks.

    overrides: optional dict of module-level constants to override for this run
    (e.g. {"LIPID_SUPPLY": 0.008, "RD_NOISE": 0.001}). Originals are restored
    after the run, so sequential calls within a worker remain isolated.
    Only whitelisted physics constants may be overridden.
    """
    _overridable = {
        "LIPID_SUPPLY", "LIPID_NOISE", "RD_NOISE", "GROWTH_PERTURB",
        "STAB_WINDOW", "STAB_DEPTH",
        "CRIT_THRESHOLD_MEAN", "CRIT_THRESHOLD_NOISE",
        "E_UPTAKE", "E_EFFICIENCY", "E_MAINTENANCE",
        "EFF_BONUS", "MAINT_BONUS", "UPT_BONUS",
        "RESOURCE_REGEN", "MAX_RESOURCE",
        "PHASE_B_CV", "PHASE_C_S", "PHASE_D_S", "PHASE_D_CV", "PHASE_D_GEN",
        "MUTATION_RATE",
    }
    _saved = {}
    if overrides:
        g = globals()
        for k, v in overrides.items():
            if k not in _overridable:
                raise ValueError(f"Override not allowed for: {k}")
            _saved[k] = g[k]
            g[k] = v
    try:
        return _run_simulation_body(seed, max_ticks, verbose)
    finally:
        if _saved:
            g = globals()
            for k, v in _saved.items():
                g[k] = v


def _run_simulation_body(seed: int, max_ticks: int, verbose: bool) -> SimResult:
    rng = np.random.default_rng(seed)
    result = SimResult(seed=seed, max_ticks=max_ticks)

    # Initialize cells
    cells: list[Cell] = []
    for _ in range(15):
        cells.append(Cell.create(rng))

    resource = MAX_RESOURCE
    phases = PhaseState()
    total_div = 0

    for tick in range(1, max_ticks + 1):
        # Resource regeneration
        resource = min(resource + RESOURCE_REGEN, MAX_RESOURCE)

        to_remove = []
        to_add = []

        for ci, c in enumerate(cells):
            c.age += 1

            # RD steps with noise
            for _ in range(RD_STEPS):
                rd_step(c, rng)

            # Growth perturbation
            resource_frac = resource / MAX_RESOURCE
            lipid_rate = LIPID_SUPPLY * resource_frac + rng.normal(0, LIPID_NOISE)
            growth = max(0.0, lipid_rate)
            c.radius += growth

            if c.age % 5 == 0:
                growth_frac = (c.radius - c.prev_radius) / c.prev_radius if c.prev_radius > 0 else 0
                if growth_frac > 0:
                    apply_growth_perturbation(c, growth_frac, rng)
                    c.prev_radius = c.radius

            # Stability measurement
            c.stab_tick += 1
            if c.stab_tick >= STAB_WINDOW:
                c.stab_tick = 0
                raw_s = compute_stability(c)
                c.pattern_s += 0.12 * (raw_s - c.pattern_s)  # EMA

            S = c.pattern_s

            # Metabolism
            uptake = E_UPTAKE * (1 + UPT_BONUS * S) * resource_frac
            eff = E_EFFICIENCY * (1 + EFF_BONUS * S)
            maint = E_MAINTENANCE * (1 - MAINT_BONUS * S)
            c.energy = np.clip(c.energy + uptake * eff - maint, DEATH_TH - 1, 15)
            resource = max(0.0, resource - uptake * 0.25)

            # Division: pure geometric instability
            rv = (MIN_RADIUS / c.radius) ** 2
            crit = CRIT_THRESHOLD_MEAN + rng.normal(0, CRIT_THRESHOLD_NOISE)
            if rv < crit and len(cells) + len(to_add) < MAX_CELLS:
                div_interval = c.age - c.last_div_age
                if c.last_div_age > 0:
                    c.division_times.append(div_interval)
                    if len(c.division_times) > 12:
                        c.division_times.pop(0)

                daughter = Cell.create(rng, c.genome.mutate(rng))
                daughter.generation = c.generation + 1
                share = 0.35 + S * 0.1
                daughter.energy = c.energy * share
                daughter.u = c.u + rng.normal(0, 0.1, N_NODES)
                daughter.v = c.v + rng.normal(0, 0.1, N_NODES)
                daughter.u = np.clip(daughter.u, 0, 2)
                daughter.v = np.clip(daughter.v, 0, 2)
                daughter.pattern_s = 0
                daughter.snapshots = []
                to_add.append(daughter)

                c.radius = MIN_RADIUS + rng.uniform(0, 1)
                c.prev_radius = c.radius
                c.energy *= (1 - share)
                c.last_div_age = c.age
                c.pattern_s *= 0.3
                c.snapshots = []
                total_div += 1

            # Death
            if c.energy <= DEATH_TH and c.age > 30:
                to_remove.append(ci)

        # Remove dead (reverse order)
        for i in sorted(to_remove, reverse=True):
            if i < len(cells):
                cells.pop(i)
        cells.extend(to_add)

        # Extinction check
        if len(cells) == 0:
            break

        # Population statistics
        if tick % SAMPLE_INTERVAL == 0 or tick == max_ticks:
            sum_s = sum(c.pattern_s for c in cells)
            max_gen = max(c.generation for c in cells) if cells else 0
            mean_s = sum_s / len(cells) if cells else 0

            cvs = []
            for c in cells:
                if len(c.division_times) >= 3:
                    times = np.array(c.division_times)
                    m = times.mean()
                    if m > 0:
                        cvs.append(times.std() / m)
            mean_cv = np.mean(cvs) if cvs else 1.0

            phase = detect_phase(mean_s, mean_cv, max_gen, phases, tick)

            result.ts_ticks.append(tick)
            result.ts_pop.append(len(cells))
            result.ts_mean_s.append(mean_s)
            result.ts_mean_cv.append(mean_cv)
            result.ts_resource.append(resource)

            if verbose and tick % 5000 == 0:
                print(f"  t={tick:6d} | pop={len(cells):3d} | S={mean_s:.3f} | CV={mean_cv:.3f} | phase={phase} | gen={max_gen}")

    # Final results
    result.phase_B_tick = phases.B_tick
    result.phase_C_tick = phases.C_tick
    result.phase_D_tick = phases.D_tick
    result.final_phase = detect_phase(
        result.ts_mean_s[-1] if result.ts_mean_s else 0,
        result.ts_mean_cv[-1] if result.ts_mean_cv else 1,
        max(c.generation for c in cells) if cells else 0,
        phases, max_ticks
    )
    result.final_pop = len(cells)
    result.final_mean_s = result.ts_mean_s[-1] if result.ts_mean_s else 0
    result.final_mean_cv = result.ts_mean_cv[-1] if result.ts_mean_cv else 1
    result.final_max_gen = max(c.generation for c in cells) if cells else 0
    result.total_divisions = total_div

    # Key hypothesis: did Clock (B) emerge before Map (C)?
    if phases.B_tick > 0 and phases.C_tick > 0:
        result.clock_before_map = phases.B_tick < phases.C_tick
    elif phases.B_tick > 0 and phases.C_tick < 0:
        result.clock_before_map = True  # B reached, C never reached
    else:
        result.clock_before_map = None  # not enough data

    return result


if __name__ == "__main__":
    print("Running single test simulation (seed=42, 20k ticks)...")
    result = run_simulation(seed=42, max_ticks=20000, verbose=True)
    print(f"\nResult: phase={result.final_phase} | B@{result.phase_B_tick} | C@{result.phase_C_tick} | D@{result.phase_D_tick}")
    print(f"Clock before Map: {result.clock_before_map}")
    print(f"Final: pop={result.final_pop} S={result.final_mean_s:.3f} CV={result.final_mean_cv:.3f} divs={result.total_divisions}")
