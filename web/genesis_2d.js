/* ════════════════════════════════════════════════════════════════════
   GENESIS ENGINE — 2D Sphere Simulation (browser port)

   JS port of genesis_engine_2d.py with the same Cell2D physics:
   Gray-Scott on a 642-vertex icosphere, growth perturbation via
   per-vertex Gaussian noise, stability via connected-components of
   v > mean, strict-sequential phase detection.

   Calibrated parameters match the Python reference (α=0.40, RD_STEPS=90).
   MAX_CELLS is capped lower here than in Python because we render every
   cell as a triangulated sphere — this is a visual showpiece, not a
   Monte-Carlo harness.
   ════════════════════════════════════════════════════════════════════ */

import {
  VERTS, FACES, N_VERTS, FACE_ADJ,
  laplaceApply, countComponentsAboveMean,
} from './icosphere.js';

/* ─── physics constants (match genesis_engine_2d.py) ─── */
const ALPHA_RESCALE   = 0.40;
const RD_STEPS        = 90;
const RD_NOISE        = 0.004;
const TOTAL_DT        = 3.0;                 // physical time per tick
const DT_SUB          = TOTAL_DT / RD_STEPS;
const NOISE_SCALE     = RD_NOISE * Math.sqrt(DT_SUB);

const MIN_RADIUS      = 8.0;
const LIPID_SUPPLY    = 0.015;
const LIPID_NOISE     = 0.003;
const GROWTH_PERTURB  = 0.15;
const MAX_RESOURCE    = 100.0;
const RESOURCE_REGEN  = 0.35;
const MAX_CELLS       = 30;              // visual cap (vs. 100 in Python)
// Note: 30 was chosen so the division-CV metric has enough division
// events (≥3 per cell) to drop under PHASE_B_CV=0.25 in reasonable live
// demo time. Below ~20 the pop saturates too fast and CV never settles.
const MUTATION_RATE   = 0.1;

const E_UPTAKE        = 0.12;
const E_EFFICIENCY    = 1.0;
const E_MAINTENANCE   = 0.07;
const EFF_BONUS       = 0.7;
const MAINT_BONUS     = 0.35;
const UPT_BONUS       = 0.12;
const DEATH_TH        = -2.0;

const CRIT_THRESHOLD_MEAN  = 0.16;
const CRIT_THRESHOLD_NOISE = 0.015;

const STAB_WINDOW = 40;
const STAB_DEPTH  = 5;

const PHASE_B_CV  = 0.25;
const PHASE_C_S   = 0.25;
const PHASE_D_S   = 0.35;
const PHASE_D_CV  = 0.30;
const PHASE_D_GEN = 5;

const SAMPLE_INTERVAL = 25;
const SPARK_LEN = 200;

/* ─── genome bounds (rescaled Da/Db) ─── */
const GENOME_BOUNDS = {
  Da: [0.02 * ALPHA_RESCALE, 0.12 * ALPHA_RESCALE],
  Db: [0.15 * ALPHA_RESCALE, 0.60 * ALPHA_RESCALE],
  f:  [0.01, 0.08],
  k:  [0.03, 0.08],
};

/* ─── RNG + utils ─── */
const randn = () => {
  const u = 1 - Math.random(), v = Math.random();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
};
const randU = (a, b) => a + Math.random() * (b - a);
const clamp = (x, lo, hi) => (x < lo ? lo : (x > hi ? hi : x));

/* ─── genome helpers ─── */
function randomGenome() {
  return {
    Da: randU(...GENOME_BOUNDS.Da),
    Db: randU(...GENOME_BOUNDS.Db),
    f:  randU(...GENOME_BOUNDS.f),
    k:  randU(...GENOME_BOUNDS.k),
  };
}
function mutateGenome(g) {
  const out = { ...g };
  for (const key of ['Da', 'Db', 'f', 'k']) {
    if (Math.random() < MUTATION_RATE) {
      out[key] = clamp(out[key] + randn() * 0.012, 0.005, 0.8);
    }
  }
  return out;
}

/* ─── Cell2D factory ─── */
function makeCell(genome = null) {
  const g = genome || randomGenome();
  const u = new Float64Array(N_VERTS);
  const v = new Float64Array(N_VERTS);
  for (let i = 0; i < N_VERTS; i++) {
    u[i] = 1.0 + randn() * 0.05;
    v[i] = Math.abs(randn() * 0.02);
  }
  // seed two mutually-nearest vertices (like the Python seed)
  const si = Math.floor(Math.random() * N_VERTS);
  let sj = 0, bestDot = -Infinity;
  const vi = VERTS[si];
  for (let j = 0; j < N_VERTS; j++) {
    if (j === si) continue;
    const vj = VERTS[j];
    const d = vi[0]*vj[0] + vi[1]*vj[1] + vi[2]*vj[2];
    if (d > bestDot) { bestDot = d; sj = j; }
  }
  v[si] = 0.5; v[sj] = 0.25;

  return {
    genome: g,
    u, v,
    // scratch buffers, re-used across RD substeps
    _nu: new Float64Array(N_VERTS),
    _nv: new Float64Array(N_VERTS),
    _lapU: new Float64Array(N_VERTS),
    _lapV: new Float64Array(N_VERTS),
    radius: MIN_RADIUS + randU(0, 2),
    prev_radius: MIN_RADIUS,
    energy: randU(1, 3),
    age: 0,
    generation: 0,
    last_div_age: 0,
    division_times: [],
    pattern_s: 0,
    snapshots: [],
    stab_tick: 0,
    // render state (screen position, sphere yaw)
    x: 0, y: 0, yaw: Math.random() * Math.PI * 2, pitch: Math.random() * 0.5 - 0.25,
  };
}

/* ─── RD step: Gray-Scott on sphere (90 forward-Euler substeps) ─── */
function rdStep(cell) {
  const { u, v, _nu, _nv, _lapU, _lapV } = cell;
  const { Da, Db, f, k } = cell.genome;
  const N = N_VERTS;

  for (let s = 0; s < RD_STEPS; s++) {
    laplaceApply(u, _lapU);
    laplaceApply(v, _lapV);
    for (let i = 0; i < N; i++) {
      const ui = u[i], vi = v[i];
      const uvv = ui * vi * vi;
      let nu = ui + DT_SUB * (Da * _lapU[i] - uvv + f * (1.0 - ui)) + randn() * NOISE_SCALE;
      let nv = vi + DT_SUB * (Db * _lapV[i] + uvv - (f + k) * vi) + randn() * NOISE_SCALE;
      if (nu < 0) nu = 0; else if (nu > 2) nu = 2;
      if (nv < 0) nv = 0; else if (nv > 2) nv = 2;
      _nu[i] = nu; _nv[i] = nv;
    }
    // swap
    u.set(_nu); v.set(_nv);
  }
}

/* ─── growth perturbation (per-vertex Gaussian noise ∝ growth_frac) ─── */
function applyGrowthPerturbation(cell, growth_frac) {
  if (growth_frac < 0.001) return;
  const shift = growth_frac * GROWTH_PERTURB;
  const sv = shift * 0.05, su = shift * 0.02;
  const { u, v } = cell;
  for (let i = 0; i < N_VERTS; i++) {
    u[i] = clamp(u[i] + randn() * su, 0, 2);
    v[i] = clamp(v[i] + randn() * sv, 0, 2);
  }
}

/* ─── stability with connected-components complexity gate ─── */
function computeStability(cell) {
  const v = cell.v, N = N_VERTS;
  let sum = 0;
  for (let i = 0; i < N; i++) sum += v[i];
  const mean = sum / N;

  let variance = 0;
  for (let i = 0; i < N; i++) { const d = v[i] - mean; variance += d * d; }
  variance /= N;
  if (variance < 0.002) return 0;

  const nComp = countComponentsAboveMean(v);
  const complexity_gate = clamp((nComp - 2) / 4, 0, 1);
  if (complexity_gate < 0.1) return 0;

  const snap = Float64Array.from(v);
  cell.snapshots.push(snap);
  if (cell.snapshots.length > STAB_DEPTH) cell.snapshots.shift();
  if (cell.snapshots.length < 3) return 0;

  let total = 0, comps = 0;
  for (let s = 0; s < cell.snapshots.length - 1; s++) {
    const hist = cell.snapshots[s];
    let hmean = 0;
    for (let i = 0; i < N; i++) hmean += hist[i];
    hmean /= N;
    let num = 0, n1 = 0, n2 = 0;
    for (let i = 0; i < N; i++) {
      const a = v[i] - mean, b = hist[i] - hmean;
      num += a * b; n1 += a * a; n2 += b * b;
    }
    const denom = Math.sqrt(n1 * n2);
    if (denom > 1e-8) { total += Math.max(0, num / denom); comps++; }
  }
  if (comps === 0) return 0;
  const mean_corr = total / comps;
  const depth_w = (cell.snapshots.length - 1) / (STAB_DEPTH - 1);
  return clamp(mean_corr * depth_w * complexity_gate, 0, 1);
}

/* ─── phase detection (strict sequential) ─── */
function detectPhase(mean_s, mean_cv, max_gen, ph, tick) {
  if (!ph.B && mean_cv > 0 && mean_cv < PHASE_B_CV) { ph.B = true; ph.B_tick = tick; }
  if (ph.B && ph.B_tick < tick && !ph.C && mean_s > PHASE_C_S) { ph.C = true; ph.C_tick = tick; }
  if (ph.C && ph.C_tick < tick && !ph.D && max_gen >= PHASE_D_GEN && mean_s > PHASE_D_S && mean_cv < PHASE_D_CV) {
    ph.D = true; ph.D_tick = tick;
  }
  return ph.D ? 'D' : (ph.C ? 'C' : (ph.B ? 'B' : 'A'));
}

/* ════════════════════════════════════════════════════════════════════
   WORLD2D — simulation state + step
   ════════════════════════════════════════════════════════════════════ */
export class World2D {
  constructor(width, height) {
    this.width = width;
    this.height = height;
    this.reset();
  }

  reset() {
    this.cells = [];
    // start with 4 cells placed around the canvas center
    const n0 = 4;
    for (let i = 0; i < n0; i++) {
      const c = makeCell();
      const ang = (i / n0) * Math.PI * 2;
      c.x = this.width * 0.5 + Math.cos(ang) * 120;
      c.y = this.height * 0.5 + Math.sin(ang) * 120;
      this.cells.push(c);
    }
    this.resource = MAX_RESOURCE;
    this.tick = 0;
    this.phases = { A: true, B: false, C: false, D: false, B_tick: -1, C_tick: -1, D_tick: -1 };
    this.total_div = 0;
    this.stats = { pop: 0, mean_s: 0, mean_cv: 1.0, resource: MAX_RESOURCE, max_gen: 0, phase: 'A' };
    this.spark = { pop: [], s: [], cv: [], res: [], ticks: [] };
    this.history = [];
    this._featuredIdx = 0;
  }

  step() {
    this.tick++;
    this.resource = Math.min(this.resource + RESOURCE_REGEN, MAX_RESOURCE);

    const toAdd = [], toRemove = [];
    for (let ci = 0; ci < this.cells.length; ci++) {
      const c = this.cells[ci];
      c.age++;

      rdStep(c);

      const resource_frac = this.resource / MAX_RESOURCE;
      const lipid_rate = LIPID_SUPPLY * resource_frac + randn() * LIPID_NOISE;
      const growth = Math.max(0, lipid_rate);
      c.radius += growth;

      if (c.age % 5 === 0) {
        const growth_frac = c.prev_radius > 0
          ? (c.radius - c.prev_radius) / c.prev_radius : 0;
        if (growth_frac > 0) {
          applyGrowthPerturbation(c, growth_frac);
          c.prev_radius = c.radius;
        }
      }

      c.stab_tick++;
      if (c.stab_tick >= STAB_WINDOW) {
        c.stab_tick = 0;
        const raw_s = computeStability(c);
        c.pattern_s += 0.12 * (raw_s - c.pattern_s);
      }
      const S = c.pattern_s;

      const uptake = E_UPTAKE * (1 + UPT_BONUS * S) * resource_frac;
      const eff    = E_EFFICIENCY * (1 + EFF_BONUS * S);
      const maint  = E_MAINTENANCE * (1 - MAINT_BONUS * S);
      c.energy = clamp(c.energy + uptake * eff - maint, DEATH_TH - 1, 15);
      this.resource = Math.max(0, this.resource - uptake * 0.25);

      const rv = Math.pow(MIN_RADIUS / c.radius, 2);
      const crit = CRIT_THRESHOLD_MEAN + randn() * CRIT_THRESHOLD_NOISE;
      if (rv < crit && this.cells.length + toAdd.length < MAX_CELLS) {
        const div_interval = c.age - c.last_div_age;
        if (c.last_div_age > 0) {
          c.division_times.push(div_interval);
          if (c.division_times.length > 12) c.division_times.shift();
        }
        const d = makeCell(mutateGenome(c.genome));
        d.generation = c.generation + 1;
        const share = 0.35 + S * 0.1;
        d.energy = c.energy * share;
        for (let i = 0; i < N_VERTS; i++) {
          d.u[i] = clamp(c.u[i] + randn() * 0.1, 0, 2);
          d.v[i] = clamp(c.v[i] + randn() * 0.1, 0, 2);
        }
        d.pattern_s = 0;
        d.snapshots = [];
        const ang = Math.random() * 2 * Math.PI;
        d.x = c.x + Math.cos(ang) * c.radius * 0.8;
        d.y = c.y + Math.sin(ang) * c.radius * 0.8;
        toAdd.push(d);

        c.radius = MIN_RADIUS + randU(0, 1);
        c.prev_radius = c.radius;
        c.energy *= (1 - share);
        c.last_div_age = c.age;
        c.pattern_s *= 0.3;
        c.snapshots = [];
        this.total_div++;
      }

      // slow sphere yaw for visual interest (purely cosmetic)
      c.yaw += 0.008;

      if (c.energy <= DEATH_TH && c.age > 30) toRemove.push(ci);
    }

    for (let i = toRemove.length - 1; i >= 0; i--) {
      const idx = toRemove[i];
      if (idx < this.cells.length) this.cells.splice(idx, 1);
    }
    for (const d of toAdd) this.cells.push(d);

    // stats + phase detection every SAMPLE_INTERVAL
    if (this.tick % SAMPLE_INTERVAL === 0 || this.cells.length === 0) {
      const pop = this.cells.length;
      let sumS = 0, maxGen = 0;
      for (const c of this.cells) { sumS += c.pattern_s; if (c.generation > maxGen) maxGen = c.generation; }
      const mean_s = pop ? sumS / pop : 0;

      const cvs = [];
      for (const c of this.cells) {
        if (c.division_times.length >= 3) {
          const ts = c.division_times;
          const m = ts.reduce((a, b) => a + b, 0) / ts.length;
          if (m > 0) {
            const varT = ts.reduce((a, b) => a + (b - m) ** 2, 0) / ts.length;
            cvs.push(Math.sqrt(varT) / m);
          }
        }
      }
      const mean_cv = cvs.length ? cvs.reduce((a, b) => a + b, 0) / cvs.length : 1.0;
      const phase = detectPhase(mean_s, mean_cv, maxGen, this.phases, this.tick);

      this.stats = { pop, mean_s, mean_cv, resource: this.resource, max_gen: maxGen, phase };
      this.spark.pop.push(pop);   if (this.spark.pop.length > SPARK_LEN) this.spark.pop.shift();
      this.spark.s.push(mean_s);  if (this.spark.s.length > SPARK_LEN) this.spark.s.shift();
      this.spark.cv.push(mean_cv);if (this.spark.cv.length > SPARK_LEN) this.spark.cv.shift();
      this.spark.res.push(this.resource); if (this.spark.res.length > SPARK_LEN) this.spark.res.shift();
      this.spark.ticks.push(this.tick);   if (this.spark.ticks.length > SPARK_LEN) this.spark.ticks.shift();

      this.history.push({ tick: this.tick, population: pop, mean_s, mean_cv,
        resource: this.resource, max_gen: maxGen, phase, total_divisions: this.total_div });
    }
  }
}

/* ════════════════════════════════════════════════════════════════════
   RENDERER — orthographic projection of each cell's sphere with
   directional-light flat shading so the geometry reads as 3D even
   when the v-field is still uniform (early-tick "phase A" state).
   ════════════════════════════════════════════════════════════════════ */

/* Directional light in view space (camera at +Z). Upper-right, slightly
   forward — gives the sphere a clear terminator without pure-black
   backhemisphere. */
const LIGHT = (() => {
  const lx = 0.35, ly = 0.55, lz = 0.75;
  const n = Math.hypot(lx, ly, lz);
  return { x: lx / n, y: ly / n, z: lz / n };
})();
const AMBIENT = 0.30;
const DIFFUSE = 0.70;

/* Base color ramp for v-concentration. Very low v (near 0) deliberately
   maps to a muted navy→teal so uniform pre-pattern cells still look
   like *colored* spheres, not black dots. High v reaches cyan→magenta. */
function vBaseColor(val) {
  const t = clamp(val / 0.6, 0, 1);
  let r, g, b;
  if (t < 0.5) {
    const s = t * 2;
    // navy → cyan
    r =  36 + ( 90 -  36) * s;
    g =  62 + (215 -  62) * s;
    b = 118 + (255 - 118) * s;
  } else {
    const s = (t - 0.5) * 2;
    // cyan → magenta
    r =  90 + (240 -  90) * s;
    g = 215 + (110 - 215) * s;
    b = 255 + (190 - 255) * s;
  }
  return [r, g, b];
}

function cellTint(S) {
  if (S >= 0.55) return '#50ddff';
  if (S >= 0.25) return '#58d78a';
  if (S >= 0.08) return '#ffb347';
  return '#e45759';
}

/* Draw one cell as a projected sphere with per-face normal-based
   diffuse shading. `radius` is in canvas pixels. */
function drawCell(ctx, cell, cx, cy, radius, yaw) {
  const cYaw = Math.cos(yaw), sYaw = Math.sin(yaw);
  const pitch = cell.pitch || 0;
  const cP = Math.cos(pitch), sP = Math.sin(pitch);

  const N = N_VERTS;
  // Rotated unit-sphere positions — these ARE the vertex normals
  // (positions on a unit sphere point outward from the origin).
  const rx = new Float32Array(N);
  const ry = new Float32Array(N);
  const rz = new Float32Array(N);
  // Screen-space projection (orthographic, camera looking at -Z)
  const px = new Float32Array(N);
  const py = new Float32Array(N);

  for (let i = 0; i < N; i++) {
    const [x, y, z] = VERTS[i];
    // yaw around Y
    const x1 = x * cYaw - z * sYaw;
    const z1 = x * sYaw + z * cYaw;
    // pitch around X
    const y2 = y * cP  - z1 * sP;
    const z2 = y * sP  + z1 * cP;
    rx[i] = x1; ry[i] = y2; rz[i] = z2;
    px[i] = cx + x1 * radius;
    py[i] = cy - y2 * radius;
  }

  // drop shadow under the sphere so it sits on the canvas
  ctx.fillStyle = 'rgba(0,0,0,0.42)';
  ctx.beginPath();
  ctx.arc(cx + radius * 0.04, cy + radius * 0.06, radius * 1.02, 0, Math.PI * 2);
  ctx.fill();

  const v = cell.v;
  const LX = LIGHT.x, LY = LIGHT.y, LZ = LIGHT.z;

  for (let fi = 0; fi < FACES.length; fi++) {
    const [a, b, c] = FACES[fi];
    // Face normal ≈ centroid direction (valid on unit sphere for small tris)
    const nx = (rx[a] + rx[b] + rx[c]) / 3;
    const ny = (ry[a] + ry[b] + ry[c]) / 3;
    const nz = (rz[a] + rz[b] + rz[c]) / 3;
    if (nz < 0) continue; // backface cull

    // diffuse component
    let nd = nx * LX + ny * LY + nz * LZ;
    if (nd < 0) nd = 0;
    const light = AMBIENT + DIFFUSE * nd;

    const vAvg = (v[a] + v[b] + v[c]) / 3;
    const [br, bg, bb] = vBaseColor(vAvg);
    const r = Math.min(255, Math.round(br * light));
    const g = Math.min(255, Math.round(bg * light));
    const bl = Math.min(255, Math.round(bb * light));
    ctx.fillStyle = `rgb(${r},${g},${bl})`;

    ctx.beginPath();
    ctx.moveTo(px[a], py[a]);
    ctx.lineTo(px[b], py[b]);
    ctx.lineTo(px[c], py[c]);
    ctx.closePath();
    ctx.fill();
  }

  // rim stroke in pattern-S class color — thin but visible
  ctx.strokeStyle = cellTint(cell.pattern_s);
  ctx.lineWidth = Math.max(1, radius * 0.014);
  ctx.beginPath();
  ctx.arc(cx, cy, radius, 0, Math.PI * 2);
  ctx.stroke();
}

/* Main scene: one large "featured" cell on the left, population grid
   of mini-cells on the right. Each mini-cell gets a gen/S label so the
   reader can see heterogeneity at a glance. */
export function drawWorld2D(ctx, world) {
  const W = world.width, H = world.height;

  // gradient backdrop
  const grad = ctx.createLinearGradient(0, 0, 0, H);
  grad.addColorStop(0, '#08101c');
  grad.addColorStop(1, '#020510');
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, W, H);

  // subtle grid
  ctx.strokeStyle = 'rgba(80,221,255,0.05)';
  ctx.lineWidth = 1;
  const step = 40;
  for (let x = step; x < W; x += step) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke(); }
  for (let y = step; y < H; y += step) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke(); }

  if (world.cells.length === 0) {
    ctx.fillStyle = 'rgba(180,200,240,0.45)';
    ctx.font = '13px "JetBrains Mono", monospace';
    ctx.textAlign = 'center';
    ctx.fillText('population extinct — press RESET', W / 2, H / 2);
    ctx.textAlign = 'left';
    return;
  }

  // featured = cell with the most developed pattern (highest S); fall back
  // to largest-radius if nothing has patterned yet (early phase A). This
  // keeps the detail view pointed at the most scientifically interesting
  // cell rather than an arbitrary one.
  let featured = world.cells[0];
  for (const c of world.cells) {
    if (c.pattern_s > featured.pattern_s
        || (c.pattern_s === featured.pattern_s && c.radius > featured.radius)) {
      featured = c;
    }
  }

  // ── FEATURED (left half) ─────────────────────────────────────────
  const leftCx = W * 0.30;
  const leftCy = H * 0.50;
  const featuredR = Math.min(240, H * 0.36);
  featured.x = leftCx; featured.y = leftCy;
  drawCell(ctx, featured, leftCx, leftCy, featuredR, featured.yaw);

  ctx.fillStyle = 'rgba(110,180,255,0.70)';
  ctx.font = '500 11px "JetBrains Mono", monospace';
  ctx.textAlign = 'center';
  ctx.fillText('FEATURED PROTOCELL', leftCx, leftCy - featuredR - 26);

  ctx.fillStyle = 'rgba(210,220,245,0.88)';
  ctx.font = '12px "JetBrains Mono", monospace';
  ctx.fillText(
    `gen ${featured.generation}  ·  S ${featured.pattern_s.toFixed(3)}  ·  age ${featured.age}`,
    leftCx, leftCy + featuredR + 30
  );
  ctx.fillStyle = 'rgba(130,170,215,0.60)';
  ctx.font = '10px "JetBrains Mono", monospace';
  ctx.fillText(
    `Da ${featured.genome.Da.toFixed(3)}  ·  Db ${featured.genome.Db.toFixed(3)}  ·  ` +
    `f ${featured.genome.f.toFixed(3)}  ·  k ${featured.genome.k.toFixed(3)}`,
    leftCx, leftCy + featuredR + 48
  );

  // ── POPULATION GRID (right half) ────────────────────────────────
  // Sized for MAX_CELLS=30 → 29 mini cells arranged 5 cols × 6 rows.
  // The featured cell is rendered separately on the left.
  const miniR  = 26;
  const gridX0 = W * 0.625;
  const gridY0 = 80;
  const cols   = 5;
  const cellW  = miniR * 2 + 10;       // 62 px
  const cellH  = miniR * 2 + 30;       // 82 px (row height incl. label)

  ctx.fillStyle = 'rgba(110,180,255,0.70)';
  ctx.font = '500 11px "JetBrains Mono", monospace';
  ctx.textAlign = 'left';
  ctx.fillText('POPULATION', gridX0 - 4, 54);
  ctx.fillStyle = 'rgba(130,170,215,0.55)';
  ctx.font = '9px "JetBrains Mono", monospace';
  ctx.fillText(`${world.cells.length} / 30 cells`, gridX0 - 4, 66);

  let idx = 0;
  for (const c of world.cells) {
    if (c === featured) continue;
    const col = idx % cols, row = Math.floor(idx / cols);
    const x = gridX0 + miniR + col * cellW;
    const y = gridY0 + miniR + row * cellH;
    c.x = x; c.y = y;
    drawCell(ctx, c, x, y, miniR, c.yaw);

    ctx.fillStyle = 'rgba(200,215,240,0.80)';
    ctx.font = '9px "JetBrains Mono", monospace';
    ctx.textAlign = 'center';
    ctx.fillText(
      `g${c.generation} · ${c.pattern_s.toFixed(2)}`,
      x, y + miniR + 14
    );
    idx++;
  }
  ctx.textAlign = 'left';
}

/* sparkline drawer — same as genesis.js but re-exported for convenience */
export function drawSpark2D(canvas, data, opts = {}) {
  const ctx = canvas.getContext('2d');
  const W = canvas.width, H = canvas.height;
  ctx.clearRect(0, 0, W, H);
  if (!data.length) return;
  const min = opts.min ?? Math.min(...data);
  const max = opts.max ?? Math.max(...data);
  const range = max - min || 1;

  if (opts.threshold !== undefined) {
    const ty = H - ((opts.threshold - min) / range) * H;
    ctx.strokeStyle = 'rgba(180,200,240,0.25)';
    ctx.setLineDash([3, 3]);
    ctx.beginPath(); ctx.moveTo(0, ty); ctx.lineTo(W, ty); ctx.stroke();
    ctx.setLineDash([]);
  }

  ctx.strokeStyle = opts.color || '#50ddff';
  ctx.lineWidth = 1.25;
  ctx.beginPath();
  for (let i = 0; i < data.length; i++) {
    const x = (i / (data.length - 1 || 1)) * W;
    const y = H - ((data[i] - min) / range) * H;
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  }
  ctx.stroke();
}
