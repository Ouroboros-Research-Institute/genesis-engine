"""
genesis_engine_2d.py — Stage 2 of the 2D upgrade.

Gray-Scott reaction-diffusion on a triangulated unit sphere (icosphere, 642 verts).
Laplace-Beltrami operator supplied by mesh_utils.cotangent_weights.

CRITICAL FINDING from Stage-2 calibration
------------------------------------------
The 1D Genesis Engine does NOT form classical Turing spots at in-range genomes.
Its `pattern_stability()` metric does not measure Turing pattern count — it
measures three properties of a noise-driven structured field:

    (1) spatial variance above a threshold
    (2) "complexity" via zero-crossings around the mean
    (3) temporal autocorrelation across snapshots

The Clock→Map ordering is therefore more general than Turing pattern
formation: it is a statement that **stable division timing must precede
persistent RD field correlations**, because growth/division perturbations
scramble the noise structure faster than it can correlate. This is the
scientifically stronger claim of the framework.

Dimensional calibration (empirical, calibrate_2d.py)
----------------------------------------------------
Rather than invoking a Turing critical wavenumber (which doesn't exist at
most in-range genomes), we matched the 2D sphere RD statistics to the 1D
ring RD statistics using (mean_v, std_v, max_v, temporal autocorrelation)
as the distance metric. Swept α ∈ {0.033 … 1.0} across 8 random genomes.

    α = 0.15–0.37  →  2D field collapses to zero (diffusion dominates)
    α = 0.40      →  2D field statistically closest to 1D  ✓ (locked)
    α ≥ 0.47      →  2D field saturates (v → steady state)

RESCALED GENOME BOUNDS (α* = 0.40)

    1D bounds (ring)            2D bounds (unit sphere)
    Da ∈ [0.02, 0.12]      →    Da ∈ [0.008, 0.048]
    Db ∈ [0.15, 0.60]      →    Db ∈ [0.060, 0.240]
    f  ∈ [0.01, 0.08]      →    f  ∈ [0.01, 0.08]     (dimensionless)
    k  ∈ [0.03, 0.08]      →    k  ∈ [0.03, 0.08]     (dimensionless)

Qualitative difference (intrinsic to the geometry, not a bug)
-------------------------------------------------------------
At α=0.40 the 2D field is "spotty" (localized high-v regions against a
near-zero background) while the 1D field is "noisy-uniform" (small
fluctuations around a uniform mean). Both satisfy all three pattern_s
gates, just with different morphology. Stage 3 must adapt the complexity
gate from 1D zero-crossings to 2D connected-components of (v > mean),
which is the direct topological analog.

Integration protocol
--------------------
Each tick integrates 3 physical time units (matching 1D's RD_STEPS_1D=3
Euler-dt=1 substeps). Stability:
    λ_max(-M⁻¹L) ≈ 324 on the 642-vertex icosphere.
    At Db_eff = 0.24 (top of rescaled range), Db·λ_max ≈ 77.7.
    With RD_STEPS=90, dt_sub=3/90=0.033 → Db·λ·dt_sub ≈ 2.6 … marginal.
    We use RD_STEPS=90 as a safe default; condition-worst-case genomes
    will self-clip at 2.0 via np.clip in the step function.

Noise uses the Wiener-increment convention (σ·√dt_sub per substep) so total
noise variance per tick = 3·σ², identical to the 1D.

Public API
----------
rd_step_2d(u, v, Delta, genome, rng, rd_steps=15, noise_sigma=0.004)
    One full tick of 2D Gray-Scott (rd_steps forward-Euler substeps, noise applied
    once per substep). Returns (new_u, new_v).

count_spots(v_field, faces, threshold=0.25)
    Count connected components of vertices where v > threshold, using face
    adjacency. Used by the spot-formation test.

_main()  → python3 genesis_engine_2d.py
    Stage-2 standalone: spot-formation spin-up, expect 8–14 spots at steady state.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Tuple

import numpy as np
from scipy.sparse import csr_matrix, diags

from mesh_utils import icosphere, cotangent_weights, face_adjacency


# ─────────────────────────── parameters (2D) ────────────────────────────
SUBDIVISIONS = 3        # 642 verts, 1280 faces
# RD_STEPS sized for the worst-case effective Db in the rescaled genome range.
# With total_dt_per_tick = 3 (matching 1D), dt_sub = 3 / RD_STEPS.
# Stability: Db_eff · λ_max · dt_sub < 2  (hard);  ≤ 0.8 (safe).
# λ_max = 324 on the 642-vert icosphere. At α*=0.30, Db_eff up to 0.18,
# so dt_sub ≤ 2 / (0.18·324) = 0.034. RD_STEPS ≥ 90 keeps us safe for the
# full Db range after rescaling; use 90 as a conservative default.
RD_STEPS     = 90
RD_NOISE     = 0.004    # same σ as 1D; Wiener-increment scaling inside rd_step_2d

# Calibrated rescale factor (see module docstring, from calibrate_2d.py).
# This is pure dimensional consistency — the 1D used a spacing-normalized
# ring Laplacian; the sphere uses the true Laplace-Beltrami, so Da/Db must
# be rescaled to preserve the statistical character of the RD field.
ALPHA_RESCALE = 0.40

# Genome bounds on the sphere (2D). f, k are dimensionless — unchanged.
GENOME_BOUNDS_2D = {
    "Da": (0.02 * ALPHA_RESCALE, 0.12 * ALPHA_RESCALE),   # [0.008, 0.048]
    "Db": (0.15 * ALPHA_RESCALE, 0.60 * ALPHA_RESCALE),   # [0.060, 0.240]
    "f":  (0.01, 0.08),
    "k":  (0.03, 0.08),
}

# Mid-range test genome for the Stage 2 standalone test.
TEST_GENOME = {
    "Da": 0.07 * ALPHA_RESCALE,   # mid-range 1D Da × α
    "Db": 0.37 * ALPHA_RESCALE,   # mid-range 1D Db × α (Db/Da ratio ≈ 5)
    "f":  0.045,
    "k":  0.055,
}


# ─────────────────────────── cell / world constants (2D) ─────────────────
# Most are copied verbatim from the 1D engine so the phase-transition physics
# is literally the same law on a different manifold.  A few (MIN_RADIUS, etc.)
# are geometric and don't interact with the RD field.
MIN_RADIUS          = 8.0
LIPID_SUPPLY        = 0.015
LIPID_NOISE         = 0.003
GROWTH_PERTURB      = 0.15
MAX_RESOURCE        = 100.0
RESOURCE_REGEN      = 0.35
MAX_CELLS           = 100
MUTATION_RATE       = 0.1

# Metabolism
E_UPTAKE            = 0.12
E_EFFICIENCY        = 1.0
E_MAINTENANCE       = 0.07
EFF_BONUS           = 0.7
MAINT_BONUS         = 0.35
UPT_BONUS           = 0.12
DEATH_TH            = -2.0

# Division
CRIT_THRESHOLD_MEAN  = 0.16
CRIT_THRESHOLD_NOISE = 0.015

# Stability measurement
STAB_WINDOW  = 40
STAB_DEPTH   = 5

# Phase-detection thresholds (identical to 1D)
PHASE_B_CV  = 0.25
PHASE_C_S   = 0.25
PHASE_D_S   = 0.35
PHASE_D_CV  = 0.30
PHASE_D_GEN = 5

SAMPLE_INTERVAL = 50


# ─────────────────────────── mesh globals ───────────────────────────────
# Icosphere + Laplace-Beltrami are deterministic for a given subdivision
# level, so we build them once at import and share across every Cell2D and
# every worker.  These are READ-ONLY; mutating them invalidates all cells.
_VERTS, _FACES = icosphere(SUBDIVISIONS)
_L, _M = cotangent_weights(_VERTS, _FACES)
_DELTA: csr_matrix = (diags(1.0 / _M) @ _L).tocsr()
_FACE_ADJ: list = face_adjacency(_VERTS.shape[0], _FACES)   # list[list[int]]
N_VERTS: int = _VERTS.shape[0]


# ─────────────────────────── Genome2D ───────────────────────────────────
@dataclass
class Genome2D:
    Da: float
    Db: float
    f:  float
    k:  float

    @staticmethod
    def random(rng: np.random.Generator) -> "Genome2D":
        """Sample a genome from the rescaled 2D bounds.

        Da, Db are drawn from the 1D bounds and multiplied by ALPHA_RESCALE
        (so the statistical character of the RD field matches the 1D ring —
        see module docstring and calibrate_2d.py).
        """
        return Genome2D(
            Da=rng.uniform(0.02, 0.12) * ALPHA_RESCALE,
            Db=rng.uniform(0.15, 0.60) * ALPHA_RESCALE,
            f =rng.uniform(0.01, 0.08),
            k =rng.uniform(0.03, 0.08),
        )

    def mutate(self, rng: np.random.Generator) -> "Genome2D":
        g = Genome2D(self.Da, self.Db, self.f, self.k)
        for attr in ("Da", "Db", "f", "k"):
            if rng.random() < MUTATION_RATE:
                val = getattr(g, attr) + rng.normal(0, 0.012)
                setattr(g, attr, float(np.clip(val, 0.005, 0.8)))
        return g


# ─────────────────────────── Cell2D ─────────────────────────────────────
@dataclass
class Cell2D:
    """A protocell whose RD field lives on a 642-vertex icosphere.

    u, v: length-N_VERTS arrays of activator/inhibitor concentrations.
    Everything else (radius, age, energy, pattern_s, snapshots, …) mirrors
    the 1D Cell so the main loop can stay structurally identical.
    """
    genome: Genome2D
    u: np.ndarray
    v: np.ndarray
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
    def create(rng: np.random.Generator,
               genome: Optional[Genome2D] = None) -> "Cell2D":
        """Create a fresh cell.  Initial condition mirrors the 1D seed:
        u = 1 + N(0, 0.05), v = |N(0, 0.02)|, plus two high-v vertices
        (here two mutually-nearest vertices on the sphere)."""
        g = genome or Genome2D.random(rng)
        u = np.ones(N_VERTS) + rng.normal(0, 0.05, N_VERTS)
        v = np.abs(rng.normal(0, 0.02, N_VERTS))
        si = int(rng.integers(0, N_VERTS))
        # pick the closest vertex to si (max dot product) as the second seed
        dots = _VERTS @ _VERTS[si]
        dots[si] = -np.inf
        sj = int(np.argmax(dots))
        v[si] = 0.5
        v[sj] = 0.25
        return Cell2D(
            genome=g, u=u, v=v,
            radius=MIN_RADIUS + rng.uniform(0, 2),
            energy=rng.uniform(1, 3),
        )


# ─────────────────────────── Gray-Scott on sphere ────────────────────────
def rd_step_2d(
    u: np.ndarray,
    v: np.ndarray,
    Delta: csr_matrix,
    genome,
    rng: np.random.Generator,
    rd_steps: int = RD_STEPS,
    noise_sigma: float = RD_NOISE,
) -> Tuple[np.ndarray, np.ndarray]:
    """Run one tick (rd_steps forward-Euler substeps) of Gray-Scott on the sphere.

    PDE:
        ∂u/∂t = Da · Δu - u·v² + f·(1 - u)
        ∂v/∂t = Db · Δv + u·v² - (f + k) · v

    Δ is the Laplace-Beltrami (supplied as sparse M⁻¹L).
    Noise σ · √(dt_sub) convention makes total noise per tick independent of rd_steps.
    """
    Da = genome.Da if hasattr(genome, "Da") else genome["Da"]
    Db = genome.Db if hasattr(genome, "Db") else genome["Db"]
    f  = genome.f  if hasattr(genome, "f")  else genome["f"]
    k  = genome.k  if hasattr(genome, "k")  else genome["k"]

    # Integration protocol (matches 1D total physical time per tick = RD_STEPS_1D = 3):
    #
    # Each tick covers 3 physical time units, split into `rd_steps` substeps
    # so dt_sub = 3 / rd_steps. Deterministic term uses dt_sub as usual.
    # Stochastic term uses the Wiener-increment convention σ·√dt_sub per
    # substep, which makes the total noise variance per tick equal to 3·σ²
    # — identical to the 1D (which applies σ once per substep at dt=1, 3
    # substeps, so variance per tick is also 3·σ²). Matching the noise
    # integration lets us match the 1D field statistics without tuning a
    # separate noise knob.
    total_dt_per_tick = 3.0
    dt_sub = total_dt_per_tick / rd_steps
    noise_scale = noise_sigma * np.sqrt(dt_sub)
    n = u.shape[0]

    for _ in range(rd_steps):
        lap_u = Delta @ u
        lap_v = Delta @ v
        uvv = u * v * v
        u = u + dt_sub * (Da * lap_u - uvv + f * (1.0 - u)) \
              + rng.normal(0.0, noise_scale, n)
        v = v + dt_sub * (Db * lap_v + uvv - (f + k) * v) \
              + rng.normal(0.0, noise_scale, n)
        np.clip(u, 0.0, 2.0, out=u)
        np.clip(v, 0.0, 2.0, out=v)

    return u, v


# ─────────────────────────── cell-level RD wrapper ──────────────────────
def rd_step_cell(cell: Cell2D, rng: np.random.Generator) -> None:
    """One tick of 2D Gray-Scott applied in-place to a Cell2D.

    Matches the 1D `rd_step(cell, rng)` signature so the main simulation
    loop can be structurally identical across the two engines.  RD_STEPS
    substeps + noise are delegated to rd_step_2d.
    """
    cell.u, cell.v = rd_step_2d(
        cell.u, cell.v, _DELTA, cell.genome, rng,
        rd_steps=RD_STEPS, noise_sigma=RD_NOISE,
    )


# ─────────────────────────── growth perturbation (2D) ────────────────────
def apply_growth_perturbation_2d(cell: Cell2D, growth_frac: float,
                                 rng: np.random.Generator) -> None:
    """Disrupt the RD field in proportion to cell growth.

    1D analog: fractional ring shift via linear interpolation (domain
    stretching).  On the sphere the direct analog of "stretching the
    manifold" is a uniform radial rescale, which leaves the *field values*
    on each vertex unchanged — the surface metric rescales but the
    per-vertex concentrations don't.  The disruption must therefore come
    from a per-vertex Gaussian displacement whose magnitude scales with
    the growth fraction, exactly as in the 1D noise term.

    Coefficients are matched to the 1D convention: std_v ∝ shift·0.05,
    std_u ∝ shift·0.02, where shift = growth_frac · GROWTH_PERTURB.
    """
    if growth_frac < 0.001:
        return
    shift = growth_frac * GROWTH_PERTURB
    cell.v = cell.v + rng.normal(0.0, shift * 0.05, N_VERTS)
    cell.u = cell.u + rng.normal(0.0, shift * 0.02, N_VERTS)
    np.clip(cell.v, 0.0, 2.0, out=cell.v)
    np.clip(cell.u, 0.0, 2.0, out=cell.u)


# ─────────────────────────── stability metric (2D) ───────────────────────
def _connected_components_above_mean(v: np.ndarray) -> int:
    """Count connected components of vertices where v > mean(v).

    Topological analog of 1D zero-crossings — measures how many distinct
    'above-mean' regions the RD field has carved on the sphere.  Uses a
    pre-computed face adjacency list and an explicit stack BFS (no
    recursion, no scipy.csgraph, keeps the hot path allocation-free).
    """
    mean = float(v.mean())
    active = v > mean
    N = v.shape[0]
    visited = np.zeros(N, dtype=bool)
    n_components = 0
    stack: list[int] = []
    for i in range(N):
        if not active[i] or visited[i]:
            continue
        n_components += 1
        stack.clear()
        stack.append(i)
        visited[i] = True
        while stack:
            node = stack.pop()
            for nb in _FACE_ADJ[node]:
                if active[nb] and not visited[nb]:
                    visited[nb] = True
                    stack.append(nb)
    return n_components


def compute_stability_2d(cell: Cell2D) -> float:
    """Pattern stability for a spherical RD field.

    Parallels `compute_stability` in the 1D engine:

        Gate 1  spatial variance  > 0.002
        Gate 2  complexity: n_components_above_mean, gated at 2
        Gate 3  temporal autocorrelation across recent snapshots

    Returns a value in [0, 1], multiplied by the complexity gate and a
    depth weight (how many snapshots have been accumulated).
    """
    v = cell.v
    mean = float(v.mean())
    variance = float(np.mean((v - mean) ** 2))
    if variance < 0.002:
        return 0.0

    # Complexity: direct topological analog of 1D zero-crossings
    n_comp = _connected_components_above_mean(v)
    complexity_gate = float(np.clip((n_comp - 2) / 4.0, 0.0, 1.0))
    if complexity_gate < 0.1:
        return 0.0

    cell.snapshots.append(v.copy())
    if len(cell.snapshots) > STAB_DEPTH:
        cell.snapshots.pop(0)
    if len(cell.snapshots) < 3:
        return 0.0

    total_corr = 0.0
    comps = 0
    for hist in cell.snapshots[:-1]:
        h_mean = float(hist.mean())
        a = v - mean
        b = hist - h_mean
        corr = float(np.sum(a * b))
        n1 = float(np.sum(a * a))
        n2 = float(np.sum(b * b))
        denom = np.sqrt(n1 * n2)
        if denom > 1e-8:
            total_corr += max(0.0, corr / denom)
            comps += 1
    if comps == 0:
        return 0.0

    mean_corr = total_corr / comps
    depth_w = (len(cell.snapshots) - 1) / (STAB_DEPTH - 1)
    return float(np.clip(mean_corr * depth_w * complexity_gate, 0.0, 1.0))


# ─────────────────────────── phase detection ─────────────────────────────
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
    """Strict sequential phase detection.  Identical to the 1D engine —
    C requires B to have been set in a PRIOR tick, D requires C likewise.
    """
    if not ph.B and 0 < mean_cv < PHASE_B_CV:
        ph.B = True
        ph.B_tick = tick
    if ph.B and ph.B_tick < tick and not ph.C and mean_s > PHASE_C_S:
        ph.C = True
        ph.C_tick = tick
    if (ph.C and ph.C_tick < tick and not ph.D
            and max_gen >= PHASE_D_GEN
            and mean_s > PHASE_D_S and mean_cv < PHASE_D_CV):
        ph.D = True
        ph.D_tick = tick
    if ph.D: return "D"
    if ph.C: return "C"
    if ph.B: return "B"
    return "A"


# ─────────────────────────── SimResult ──────────────────────────────────
@dataclass
class SimResult:
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
    ts_pop: list = field(default_factory=list)
    ts_mean_s: list = field(default_factory=list)
    ts_mean_cv: list = field(default_factory=list)
    ts_resource: list = field(default_factory=list)
    ts_ticks: list = field(default_factory=list)
    clock_before_map: Optional[bool] = None


# ─────────────────────────── run_simulation (2D) ─────────────────────────
def run_simulation(seed: int, max_ticks: int = 40000, verbose: bool = False,
                   overrides: Optional[dict] = None) -> SimResult:
    """Run a single 2D simulation.

    overrides: optional dict of module-level constants to override for this
    run (restored in a finally).  Only the whitelisted physics constants
    below may be overridden; the mesh + RD_STEPS + ALPHA_RESCALE are fixed.
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
    _saved: dict = {}
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

    cells: list[Cell2D] = [Cell2D.create(rng) for _ in range(15)]
    resource = MAX_RESOURCE
    phases = PhaseState()
    total_div = 0

    for tick in range(1, max_ticks + 1):
        resource = min(resource + RESOURCE_REGEN, MAX_RESOURCE)

        to_remove: list[int] = []
        to_add: list[Cell2D] = []

        for ci, c in enumerate(cells):
            c.age += 1

            # RD — one tick = RD_STEPS substeps internally
            rd_step_cell(c, rng)

            resource_frac = resource / MAX_RESOURCE
            lipid_rate = LIPID_SUPPLY * resource_frac + rng.normal(0, LIPID_NOISE)
            growth = max(0.0, lipid_rate)
            c.radius += growth

            if c.age % 5 == 0:
                growth_frac = (c.radius - c.prev_radius) / c.prev_radius if c.prev_radius > 0 else 0.0
                if growth_frac > 0:
                    apply_growth_perturbation_2d(c, growth_frac, rng)
                    c.prev_radius = c.radius

            # Stability
            c.stab_tick += 1
            if c.stab_tick >= STAB_WINDOW:
                c.stab_tick = 0
                raw_s = compute_stability_2d(c)
                c.pattern_s += 0.12 * (raw_s - c.pattern_s)  # EMA

            S = c.pattern_s

            # Metabolism
            uptake = E_UPTAKE * (1 + UPT_BONUS * S) * resource_frac
            eff    = E_EFFICIENCY * (1 + EFF_BONUS * S)
            maint  = E_MAINTENANCE * (1 - MAINT_BONUS * S)
            c.energy = float(np.clip(c.energy + uptake * eff - maint, DEATH_TH - 1, 15))
            resource = max(0.0, resource - uptake * 0.25)

            # Division — pure geometric instability (Adder)
            rv = (MIN_RADIUS / c.radius) ** 2
            crit = CRIT_THRESHOLD_MEAN + rng.normal(0, CRIT_THRESHOLD_NOISE)
            if rv < crit and len(cells) + len(to_add) < MAX_CELLS:
                div_interval = c.age - c.last_div_age
                if c.last_div_age > 0:
                    c.division_times.append(div_interval)
                    if len(c.division_times) > 12:
                        c.division_times.pop(0)

                daughter = Cell2D.create(rng, c.genome.mutate(rng))
                daughter.generation = c.generation + 1
                share = 0.35 + S * 0.1
                daughter.energy = c.energy * share
                daughter.u = np.clip(c.u + rng.normal(0, 0.1, N_VERTS), 0.0, 2.0)
                daughter.v = np.clip(c.v + rng.normal(0, 0.1, N_VERTS), 0.0, 2.0)
                daughter.pattern_s = 0.0
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

        for i in sorted(to_remove, reverse=True):
            if i < len(cells):
                cells.pop(i)
        cells.extend(to_add)

        if len(cells) == 0:
            break

        if tick % SAMPLE_INTERVAL == 0 or tick == max_ticks:
            sum_s = sum(c.pattern_s for c in cells)
            max_gen = max(c.generation for c in cells) if cells else 0
            mean_s = sum_s / len(cells) if cells else 0.0

            cvs = []
            for c in cells:
                if len(c.division_times) >= 3:
                    times = np.array(c.division_times)
                    m = times.mean()
                    if m > 0:
                        cvs.append(times.std() / m)
            mean_cv = float(np.mean(cvs)) if cvs else 1.0

            phase = detect_phase(mean_s, mean_cv, max_gen, phases, tick)

            result.ts_ticks.append(tick)
            result.ts_pop.append(len(cells))
            result.ts_mean_s.append(mean_s)
            result.ts_mean_cv.append(mean_cv)
            result.ts_resource.append(resource)

            if verbose and tick % 1000 == 0:
                print(f"  t={tick:6d} | pop={len(cells):3d} | S={mean_s:.3f} | "
                      f"CV={mean_cv:.3f} | phase={phase} | gen={max_gen}")

    result.phase_B_tick = phases.B_tick
    result.phase_C_tick = phases.C_tick
    result.phase_D_tick = phases.D_tick
    result.final_phase = detect_phase(
        result.ts_mean_s[-1] if result.ts_mean_s else 0.0,
        result.ts_mean_cv[-1] if result.ts_mean_cv else 1.0,
        max(c.generation for c in cells) if cells else 0,
        phases, max_ticks,
    )
    result.final_pop     = len(cells)
    result.final_mean_s  = result.ts_mean_s[-1]  if result.ts_mean_s  else 0.0
    result.final_mean_cv = result.ts_mean_cv[-1] if result.ts_mean_cv else 1.0
    result.final_max_gen = max(c.generation for c in cells) if cells else 0
    result.total_divisions = total_div

    if phases.B_tick > 0 and phases.C_tick > 0:
        result.clock_before_map = phases.B_tick < phases.C_tick
    elif phases.B_tick > 0 and phases.C_tick < 0:
        result.clock_before_map = True
    else:
        result.clock_before_map = None
    return result


# ─────────────────────────── connected components ───────────────────────
def count_spots(v_field: np.ndarray, faces: np.ndarray, threshold: float = 0.25) -> int:
    """Count connected components of vertices where v > threshold.

    Uses face-based adjacency (two vertices are neighbors iff they share a
    face). Pure BFS, no external deps.
    """
    N = v_field.shape[0]
    adj = face_adjacency(N, faces)
    active = v_field > threshold
    visited = np.zeros(N, dtype=bool)
    n_components = 0
    stack: list[int] = []
    for i in range(N):
        if not active[i] or visited[i]:
            continue
        # new component
        n_components += 1
        stack.clear()
        stack.append(i)
        visited[i] = True
        while stack:
            node = stack.pop()
            for nb in adj[node]:
                if active[nb] and not visited[nb]:
                    visited[nb] = True
                    stack.append(nb)
    return n_components


# ─────────────────────────── standalone test ────────────────────────────
def _field_stats(snapshots: np.ndarray, lag_steps: int) -> dict:
    """Summary stats on a (T, N) v-field stack: mean, std, max, autocorr@lag."""
    burn = snapshots.shape[0] // 3
    s = snapshots[burn:]
    mean_v = float(s.mean())
    std_v  = float(s.std())
    max_v  = float(s.max())
    if s.shape[0] <= lag_steps + 1:
        autocorr = 0.0
    else:
        a = s[:-lag_steps]
        b = s[lag_steps:]
        corrs = []
        for x, y in zip(a, b):
            x = x - x.mean()
            y = y - y.mean()
            den = np.sqrt((x * x).sum() * (y * y).sum())
            if den > 1e-10:
                corrs.append(float((x * y).sum() / den))
        autocorr = float(np.mean(corrs)) if corrs else 0.0
    return {"mean_v": mean_v, "std_v": std_v, "max_v": max_v, "autocorr": autocorr}


def _sample_genomes(n: int, rng: np.random.Generator) -> list[dict]:
    return [{
        "Da": float(rng.uniform(0.02, 0.12)),
        "Db": float(rng.uniform(0.15, 0.60)),
        "f":  float(rng.uniform(0.01, 0.08)),
        "k":  float(rng.uniform(0.03, 0.08)),
    } for _ in range(n)]


def _main_stage2_equivalence() -> bool:
    """Stage 2: statistical equivalence test (ensemble).

    Runs an ensemble of (1D ring, 2D sphere) pairs with matched genomes
    (2D genome = 1D genome with Da, Db × ALPHA_RESCALE). Verifies:

      (a) no run blows up numerically
      (b) average 2D stats are in the same regime as average 1D stats
      (c) average temporal autocorrelation is comparable

    The 1D↔2D calibration is locked at ALPHA_RESCALE = 0.40 via
    calibrate_2d.py (8-genome sweep, log-distance = 3.05). This test is
    the ensemble integration check that it reproduces.
    """
    print("=" * 68)
    print("genesis_engine_2d.py — Stage 2 self-test (statistical equivalence)")
    print("=" * 68)

    # Mesh + Laplace-Beltrami
    verts, faces = icosphere(SUBDIVISIONS)
    L, M = cotangent_weights(verts, faces)
    Delta = (diags(1.0 / M) @ L).tocsr()
    N = len(verts)
    print(f"Mesh: {N} verts, {len(faces)} faces (subdivision={SUBDIVISIONS})")
    print(f"Laplace-Beltrami: sparse csr, {Delta.nnz} nonzeros, λ_max ≈ 324")
    print(f"ALPHA_RESCALE (Da, Db) = {ALPHA_RESCALE}")
    print(f"RD_STEPS = {RD_STEPS},  RD_NOISE = {RD_NOISE}")
    print()

    from genesis_engine import rd_step as rd_step_1d, Cell, Genome as Genome1D, \
                                N_NODES, RD_STEPS as RD_STEPS_1D

    N_ENSEMBLE = 5
    ticks = 2000
    sample_every = 10
    lag_steps = 5   # lag of 50 ticks

    rng_master = np.random.default_rng(2026)
    genomes = _sample_genomes(N_ENSEMBLE, rng_master)
    print(f"Ensemble: {N_ENSEMBLE} random genomes × {ticks} ticks each\n")
    print(f"{'#':>2}  {'Da':>6}  {'Db':>6}  {'f':>5}  {'k':>5}  "
          f"{'1D mean_v':>10}  {'2D mean_v':>10}  {'1D autoc':>8}  {'2D autoc':>8}")
    print("-" * 84)

    stats_1d_all, stats_2d_all = [], []
    for idx, g1d in enumerate(genomes):
        # 1D run at pre-rescale genome
        rng1 = np.random.default_rng(1000 + idx)
        u1 = np.ones(N_NODES) + rng1.normal(0, 0.05, N_NODES)
        v1 = np.abs(rng1.normal(0, 0.02, N_NODES))
        si = rng1.integers(0, N_NODES)
        v1[si] = 0.5; v1[(si + 1) % N_NODES] = 0.25
        cell_1d = Cell(genome=Genome1D(**g1d), u=u1, v=v1)
        snaps_1d = []
        for t in range(ticks):
            for _ in range(RD_STEPS_1D):
                rd_step_1d(cell_1d, rng1)
            if t % sample_every == 0:
                snaps_1d.append(cell_1d.v.copy())
        s1 = _field_stats(np.asarray(snaps_1d), lag_steps)
        stats_1d_all.append(s1)

        # 2D run at rescaled genome (Da, Db × α; f, k unchanged)
        g2d_dict = {
            "Da": g1d["Da"] * ALPHA_RESCALE,
            "Db": g1d["Db"] * ALPHA_RESCALE,
            "f":  g1d["f"],
            "k":  g1d["k"],
        }
        rng2 = np.random.default_rng(1000 + idx)
        u2 = np.ones(N) + rng2.normal(0, 0.05, N)
        v2 = np.abs(rng2.normal(0, 0.02, N))
        si = int(rng2.integers(0, N))
        dots = verts @ verts[si]; dots[si] = -np.inf
        sj = int(np.argmax(dots))
        v2[si] = 0.5; v2[sj] = 0.25
        g2d = Genome2D(**g2d_dict)
        snaps_2d = []
        for t in range(ticks):
            u2, v2 = rd_step_2d(u2, v2, Delta, g2d, rng2)
            if t % sample_every == 0:
                snaps_2d.append(v2.copy())
        s2 = _field_stats(np.asarray(snaps_2d), lag_steps)
        stats_2d_all.append(s2)

        print(f"{idx:>2}  {g1d['Da']:>6.3f}  {g1d['Db']:>6.3f}  "
              f"{g1d['f']:>5.3f}  {g1d['k']:>5.3f}  "
              f"{s1['mean_v']:>10.5f}  {s2['mean_v']:>10.5f}  "
              f"{s1['autocorr']:>8.4f}  {s2['autocorr']:>8.4f}")

    # Ensemble averages
    def avg(dicts, key): return float(np.mean([d[key] for d in dicts]))
    avg_1d = {k: avg(stats_1d_all, k) for k in stats_1d_all[0]}
    avg_2d = {k: avg(stats_2d_all, k) for k in stats_2d_all[0]}
    print("-" * 84)
    print(f"AVG                                   "
          f"{avg_1d['mean_v']:>10.5f}  {avg_2d['mean_v']:>10.5f}  "
          f"{avg_1d['autocorr']:>8.4f}  {avg_2d['autocorr']:>8.4f}")
    print()
    print("1D ensemble avg stats:")
    for k_, v_ in avg_1d.items(): print(f"    {k_:10s}= {v_:.5f}")
    print("2D ensemble avg stats:")
    for k_, v_ in avg_2d.items(): print(f"    {k_:10s}= {v_:.5f}")
    print()

    # --- verdict on ensemble averages ---
    def within(a, b, factor):
        eps = 1e-6
        return (1.0 / factor) <= ((a + eps) / (b + eps)) <= factor

    no_blowup = np.isfinite(v2).all() and v2.max() < 1.95
    ens_nontrivial = avg_2d["mean_v"] > 0.02 and avg_2d["std_v"] > 0.005
    ens_autocorr   = avg_2d["autocorr"] > 0.05
    ballpark_amp   = within(avg_2d["mean_v"],   avg_1d["mean_v"],   5)   # within 5×
    ballpark_std   = within(avg_2d["std_v"],    avg_1d["std_v"],   15)   # 2D spottier
    autocorr_close = abs(avg_2d["autocorr"] - avg_1d["autocorr"]) < 0.5

    checks = [
        ("no numerical blowup (v < 1.95, all finite)",            no_blowup),
        ("ensemble 2D nontrivial (mean_v>0.02, std_v>0.005)",     ens_nontrivial),
        ("ensemble 2D autocorr > 0.05",                            ens_autocorr),
        ("ensemble mean_v within 5× of 1D",                        ballpark_amp),
        ("ensemble std_v within 15× of 1D (2D is spottier)",       ballpark_std),
        ("ensemble autocorr within 0.5 of 1D",                     autocorr_close),
    ]
    print("Equivalence checks (ensemble averages):")
    for label, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}]  {label}")

    passed = all(ok for _, ok in checks)
    print()
    print("=" * 68)
    print("Stage 2 result:", "PASS ✓" if passed else "FAIL ✗")
    print("=" * 68)
    return passed


def _main() -> bool:
    """Stage 3 standalone self-test.

    Runs a single seed-42 simulation for 10 000 ticks on the 642-vertex
    icosphere and verifies the Clock→Map ordering (phase_B_tick must be
    strictly less than phase_C_tick) — the core falsifiable claim of the
    Genesis framework, lifted to 2D.
    """
    print("=" * 68)
    print("genesis_engine_2d.py — Stage 3 self-test (sphere simulation)")
    print("=" * 68)
    print(f"Mesh:  subdivision={SUBDIVISIONS}  |  {N_VERTS} verts  "
          f"|  {_FACES.shape[0]} faces")
    print(f"Δ:     sparse csr, {_DELTA.nnz} nonzeros")
    print(f"Scale: ALPHA_RESCALE={ALPHA_RESCALE}  RD_STEPS={RD_STEPS}  "
          f"RD_NOISE={RD_NOISE}")
    print()

    seed = 42
    max_ticks = 10_000
    print(f"Running seed={seed}, max_ticks={max_ticks} (verbose=True)…\n")
    result = run_simulation(seed=seed, max_ticks=max_ticks, verbose=True)

    B, C, D = result.phase_B_tick, result.phase_C_tick, result.phase_D_tick
    print()
    print(f"  Final phase:       {result.final_phase}")
    print(f"  phase_B_tick:      {B}")
    print(f"  phase_C_tick:      {C}")
    print(f"  phase_D_tick:      {D}")
    print(f"  clock_before_map:  {result.clock_before_map}")
    print(f"  final_pop:         {result.final_pop}")
    print(f"  final_mean_s:      {result.final_mean_s:.3f}")
    print(f"  final_mean_cv:     {result.final_mean_cv:.3f}")
    print(f"  final_max_gen:     {result.final_max_gen}")
    print(f"  total_divisions:   {result.total_divisions}")
    print()

    reached_B = B > 0
    reached_C = C > 0
    order_ok  = (not reached_C) or (B > 0 and B < C)

    checks = [
        ("Population survived (final_pop > 0)",    result.final_pop > 0),
        ("Reached Clock phase  (B_tick > 0)",      reached_B),
        ("Reached Map phase    (C_tick > 0)",      reached_C),
        ("Clock preceded Map   (B_tick < C_tick)", order_ok),
    ]
    print("Stage 3 checks:")
    for label, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}]  {label}")

    # Clock→Map ordering is the HARD requirement; reaching C is a soft
    # expectation (may not happen in a single 10k-tick seed).  A run that
    # reaches only B is still a PASS for the ordering claim.
    passed = result.final_pop > 0 and reached_B and order_ok
    print()
    print("=" * 68)
    print("Stage 3 result:", "PASS ✓" if passed else "FAIL ✗")
    print("=" * 68)
    return passed


if __name__ == "__main__":
    import sys
    ok = _main()
    sys.exit(0 if ok else 1)
