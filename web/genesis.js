/* ════════════════════════════════════════════════════════════════════
   GENESIS ENGINE — Live Simulation (JS port of genesis_engine.py)
   Physics must exactly mirror the validated Python reference.
   Farina 2025
   ════════════════════════════════════════════════════════════════════ */

/* ─── Constants (matched to genesis_engine.py) ─── */
const N_NODES = 24;
const MIN_RADIUS = 8.0;
const LIPID_SUPPLY = 0.015;
const LIPID_NOISE = 0.003;
const RD_STEPS = 3;
const RD_NOISE = 0.004;
const GROWTH_PERTURB = 0.15;
const MAX_RESOURCE = 100.0;
const RESOURCE_REGEN = 0.35;
const MAX_CELLS = 100;
const MUTATION_RATE = 0.1;

const E_UPTAKE = 0.12;
const E_EFFICIENCY = 1.0;
const E_MAINTENANCE = 0.07;
const EFF_BONUS = 0.7;
const MAINT_BONUS = 0.35;
const UPT_BONUS = 0.12;
const DEATH_TH = -2.0;

const CRIT_THRESHOLD_MEAN = 0.16;
const CRIT_THRESHOLD_NOISE = 0.015;

const STAB_WINDOW = 40;
const STAB_DEPTH = 5;

const PHASE_B_CV = 0.25;
const PHASE_C_S  = 0.25;
const PHASE_D_S  = 0.35;
const PHASE_D_CV = 0.30;
const PHASE_D_GEN = 5;

const SAMPLE_INTERVAL = 25;   // for sparklines (denser than MC's 50)
const SPARK_LEN = 200;

/* ─── RNG ─── */
const rand   = () => Math.random();
const randn  = () => { const u = 1 - Math.random(), v = Math.random(); return Math.sqrt(-2*Math.log(u))*Math.cos(2*Math.PI*v); };
const randU  = (a,b) => a + Math.random()*(b-a);
const randi  = (a,b) => Math.floor(a + Math.random()*(b-a));
const clamp  = (x,lo,hi) => x<lo?lo:(x>hi?hi:x);

/* ─── Genome ─── */
function randomGenome() {
  return { Da: randU(0.02,0.12), Db: randU(0.15,0.6), f: randU(0.01,0.08), k: randU(0.03,0.08) };
}
function mutateGenome(g) {
  const out = { ...g };
  for (const key of ['Da','Db','f','k']) {
    if (rand() < MUTATION_RATE) out[key] = clamp(out[key] + randn()*0.012, 0.005, 0.8);
  }
  return out;
}

/* ─── Cell factory ─── */
function makeCell(genome = null) {
  const g = genome || randomGenome();
  const u = new Float32Array(N_NODES);
  const v = new Float32Array(N_NODES);
  for (let i = 0; i < N_NODES; i++) { u[i] = 1.0 + randn()*0.05; v[i] = Math.abs(randn()*0.02); }
  const si = randi(0, N_NODES);
  v[si] = 0.5; v[(si+1) % N_NODES] = 0.25;
  return {
    genome: g,
    u, v,
    radius: MIN_RADIUS + randU(0,2),
    prev_radius: MIN_RADIUS,
    energy: randU(1,3),
    age: 0,
    generation: 0,
    last_div_age: 0,
    division_times: [],
    pattern_s: 0,
    snapshots: [],
    stab_tick: 0,
    // rendering state
    x: 0, y: 0, vx: 0, vy: 0,
  };
}

/* ─── RD step: Gray-Scott on a ring with continuous noise ─── */
function rdStep(cell) {
  const { u, v } = cell;
  const { Da, Db, f, k } = cell.genome;
  const n = N_NODES;
  const nu = new Float32Array(n), nv = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const il = (i-1+n)%n, ir = (i+1)%n;
    const lapU = u[il] + u[ir] - 2*u[i];
    const lapV = v[il] + v[ir] - 2*v[i];
    const uvv  = u[i]*v[i]*v[i];
    nu[i] = u[i] + (Da*lapU - uvv + f*(1.0 - u[i])) + randn()*RD_NOISE;
    nv[i] = v[i] + (Db*lapV + uvv - (f+k)*v[i]) + randn()*RD_NOISE;
  }
  for (let i = 0; i < n; i++) {
    cell.u[i] = clamp(nu[i], 0, 2);
    cell.v[i] = clamp(nv[i], 0, 2);
  }
}

/* ─── Growth perturbation: fractional shift ─── */
function applyGrowthPerturbation(cell, growth_frac) {
  if (growth_frac < 0.001) return;
  const shift = growth_frac * GROWTH_PERTURB;
  const n = N_NODES;
  const nu = new Float32Array(n), nv = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const src = (i + shift) % n;
    const lo  = Math.floor(src) % n;
    const hi  = (lo + 1) % n;
    const frac = src - Math.floor(src);
    nv[i] = clamp(cell.v[lo]*(1-frac) + cell.v[hi]*frac + randn()*shift*0.05, 0, 2);
    nu[i] = clamp(cell.u[lo]*(1-frac) + cell.u[hi]*frac + randn()*shift*0.02, 0, 2);
  }
  cell.u = nu; cell.v = nv;
}

/* ─── Stability: variance gate + complexity gate + temporal autocorr ─── */
function computeStability(cell) {
  const v = cell.v, n = N_NODES;
  let mean = 0;
  for (let i = 0; i < n; i++) mean += v[i];
  mean /= n;
  let variance = 0;
  for (let i = 0; i < n; i++) { const d = v[i]-mean; variance += d*d; }
  variance /= n;
  if (variance < 0.002) return 0;

  // complexity: zero-crossings around mean
  let crossings = 0, prev = Math.sign(v[0]-mean);
  for (let i = 1; i < n; i++) { const s = Math.sign(v[i]-mean); if (s !== prev && s !== 0) crossings++; prev = s || prev; }
  // wrap
  if (Math.sign(v[0]-mean) !== Math.sign(v[n-1]-mean)) crossings++;
  const complexity_gate = clamp((crossings - 2) / 4, 0, 1);
  if (complexity_gate < 0.1) return 0;

  // snapshot buffer
  const snap = Float32Array.from(v);
  cell.snapshots.push(snap);
  if (cell.snapshots.length > STAB_DEPTH) cell.snapshots.shift();
  if (cell.snapshots.length < 3) return 0;

  // temporal autocorr across all prior snapshots
  let total = 0, comps = 0;
  for (let s = 0; s < cell.snapshots.length - 1; s++) {
    const hist = cell.snapshots[s];
    let hmean = 0;
    for (let i = 0; i < n; i++) hmean += hist[i];
    hmean /= n;
    let num = 0, n1 = 0, n2 = 0;
    for (let i = 0; i < n; i++) {
      const a = v[i] - mean, b = hist[i] - hmean;
      num += a*b; n1 += a*a; n2 += b*b;
    }
    const denom = Math.sqrt(n1*n2);
    if (denom > 1e-8) { total += Math.max(0, num/denom); comps++; }
  }
  if (comps === 0) return 0;
  const mean_corr = total / comps;
  const depth_w = (cell.snapshots.length - 1) / (STAB_DEPTH - 1);
  return clamp(mean_corr * depth_w * complexity_gate, 0, 1);
}

/* ─── Phase detection ─── */
function detectPhase(mean_s, mean_cv, max_gen, ph, tick) {
  if (!ph.B && mean_cv > 0 && mean_cv < PHASE_B_CV) { ph.B = true; ph.B_tick = tick; }
  if (ph.B && ph.B_tick < tick && !ph.C && mean_s > PHASE_C_S) { ph.C = true; ph.C_tick = tick; }
  if (ph.C && ph.C_tick < tick && !ph.D && max_gen >= PHASE_D_GEN && mean_s > PHASE_D_S && mean_cv < PHASE_D_CV) {
    ph.D = true; ph.D_tick = tick;
  }
  return ph.D ? 'D' : (ph.C ? 'C' : (ph.B ? 'B' : 'A'));
}

/* ════════════════════════════════════════════════════════════════════
   WORLD  —  simulation state + step
   ════════════════════════════════════════════════════════════════════ */
export class World {
  constructor(width, height) {
    this.width = width;
    this.height = height;
    this.reset();
  }

  reset() {
    this.cells = [];
    for (let i = 0; i < 15; i++) {
      const c = makeCell();
      c.x = this.width*0.5 + randn()*60;
      c.y = this.height*0.5 + randn()*60;
      this.cells.push(c);
    }
    this.resource = MAX_RESOURCE;
    this.tick = 0;
    this.phases = { A:true, B:false, C:false, D:false, B_tick:-1, C_tick:-1, D_tick:-1 };
    this.total_div = 0;

    // stats & sparklines
    this.stats = { pop:0, mean_s:0, mean_cv:1.0, resource:MAX_RESOURCE, max_gen:0, phase:'A' };
    this.spark = { pop:[], s:[], cv:[], res:[], ticks:[] };
    // full unbounded history for CSV export (sampled every SAMPLE_INTERVAL ticks)
    this.history = [];
  }

  step() {
    this.tick++;
    this.resource = Math.min(this.resource + RESOURCE_REGEN, MAX_RESOURCE);

    const toAdd = [], toRemove = [];
    for (let ci = 0; ci < this.cells.length; ci++) {
      const c = this.cells[ci];
      c.age++;

      for (let r = 0; r < RD_STEPS; r++) rdStep(c);

      const resource_frac = this.resource / MAX_RESOURCE;
      const lipid_rate = LIPID_SUPPLY * resource_frac + randn()*LIPID_NOISE;
      const growth = Math.max(0, lipid_rate);
      c.radius += growth;

      if (c.age % 5 === 0) {
        const growth_frac = c.prev_radius > 0 ? (c.radius - c.prev_radius) / c.prev_radius : 0;
        if (growth_frac > 0) { applyGrowthPerturbation(c, growth_frac); c.prev_radius = c.radius; }
      }

      c.stab_tick++;
      if (c.stab_tick >= STAB_WINDOW) {
        c.stab_tick = 0;
        const raw_s = computeStability(c);
        c.pattern_s += 0.12 * (raw_s - c.pattern_s); // EMA
      }

      const S = c.pattern_s;

      // metabolism (S affects ENERGY only, not growth)
      const uptake = E_UPTAKE * (1 + UPT_BONUS * S) * resource_frac;
      const eff    = E_EFFICIENCY * (1 + EFF_BONUS * S);
      const maint  = E_MAINTENANCE * (1 - MAINT_BONUS * S);
      c.energy = clamp(c.energy + uptake*eff - maint, DEATH_TH - 1, 15);
      this.resource = Math.max(0, this.resource - uptake*0.25);

      // division: pure geometric instability
      const rv = Math.pow(MIN_RADIUS / c.radius, 2);
      const crit = CRIT_THRESHOLD_MEAN + randn()*CRIT_THRESHOLD_NOISE;
      if (rv < crit && this.cells.length + toAdd.length < MAX_CELLS) {
        const div_interval = c.age - c.last_div_age;
        if (c.last_div_age > 0) {
          c.division_times.push(div_interval);
          if (c.division_times.length > 12) c.division_times.shift();
        }
        const daughter = makeCell(mutateGenome(c.genome));
        daughter.generation = c.generation + 1;
        const share = 0.35 + S * 0.1;
        daughter.energy = c.energy * share;
        for (let i = 0; i < N_NODES; i++) {
          daughter.u[i] = clamp(c.u[i] + randn()*0.1, 0, 2);
          daughter.v[i] = clamp(c.v[i] + randn()*0.1, 0, 2);
        }
        daughter.pattern_s = 0;
        daughter.snapshots = [];

        // place daughter near parent with a small push
        const ang = Math.random() * 2 * Math.PI;
        daughter.x = c.x + Math.cos(ang)*c.radius*0.6;
        daughter.y = c.y + Math.sin(ang)*c.radius*0.6;
        daughter.vx = Math.cos(ang)*0.4;
        daughter.vy = Math.sin(ang)*0.4;
        c.vx = -Math.cos(ang)*0.4;
        c.vy = -Math.sin(ang)*0.4;

        toAdd.push(daughter);

        c.radius = MIN_RADIUS + randU(0, 1);
        c.prev_radius = c.radius;
        c.energy *= (1 - share);
        c.last_div_age = c.age;
        c.pattern_s *= 0.3;
        c.snapshots = [];
        this.total_div++;
      }

      if (c.energy <= DEATH_TH && c.age > 30) toRemove.push(ci);
    }

    // remove dead
    for (let i = toRemove.length - 1; i >= 0; i--) this.cells.splice(toRemove[i], 1);
    for (const d of toAdd) this.cells.push(d);

    // physics (gentle repulsion + damping + bounds)
    this._layoutStep();

    // stats
    if (this.tick % 1 === 0) {
      const pop = this.cells.length;
      let sum_s = 0, max_gen = 0;
      const cvs = [];
      for (const c of this.cells) {
        sum_s += c.pattern_s;
        if (c.generation > max_gen) max_gen = c.generation;
        if (c.division_times.length >= 3) {
          let m = 0; for (const t of c.division_times) m += t; m /= c.division_times.length;
          let vsum = 0; for (const t of c.division_times) vsum += (t-m)*(t-m);
          const sd = Math.sqrt(vsum / c.division_times.length);
          if (m > 0) cvs.push(sd / m);
        }
      }
      const mean_s = pop > 0 ? sum_s/pop : 0;
      let mean_cv = 1.0;
      if (cvs.length) { let s=0; for (const x of cvs) s+=x; mean_cv = s/cvs.length; }

      const phase = detectPhase(mean_s, mean_cv, max_gen, this.phases, this.tick);

      this.stats = { pop, mean_s, mean_cv, resource: this.resource, max_gen, phase };

      if (this.tick % SAMPLE_INTERVAL === 0) {
        this.spark.ticks.push(this.tick);
        this.spark.pop.push(pop);
        this.spark.s.push(mean_s);
        this.spark.cv.push(mean_cv);
        this.spark.res.push(this.resource);
        if (this.spark.ticks.length > SPARK_LEN) {
          this.spark.ticks.shift(); this.spark.pop.shift();
          this.spark.s.shift(); this.spark.cv.shift(); this.spark.res.shift();
        }
        // unbounded history for CSV export
        this.history.push({
          tick: this.tick, population: pop,
          mean_s: mean_s, mean_cv: mean_cv,
          resource: this.resource, max_gen: max_gen,
          phase: phase, total_divisions: this.total_div,
        });
      }
    }
  }

  _layoutStep() {
    const cells = this.cells;
    // gentle repulsion between overlapping cells
    for (let i = 0; i < cells.length; i++) {
      for (let j = i+1; j < cells.length; j++) {
        const a = cells[i], b = cells[j];
        const dx = b.x - a.x, dy = b.y - a.y;
        const d = Math.sqrt(dx*dx + dy*dy) + 1e-6;
        const minD = (a.radius + b.radius) * 1.2;
        if (d < minD) {
          const push = (minD - d) * 0.06;
          const nx = dx/d, ny = dy/d;
          a.vx -= nx*push; a.vy -= ny*push;
          b.vx += nx*push; b.vy += ny*push;
        }
      }
    }
    const pad = 28;
    for (const c of cells) {
      c.x += c.vx; c.y += c.vy;
      c.vx *= 0.88; c.vy *= 0.88;
      // bounds
      if (c.x < pad) { c.x = pad; c.vx = Math.abs(c.vx)*0.5; }
      if (c.x > this.width - pad) { c.x = this.width - pad; c.vx = -Math.abs(c.vx)*0.5; }
      if (c.y < pad) { c.y = pad; c.vy = Math.abs(c.vy)*0.5; }
      if (c.y > this.height - pad) { c.y = this.height - pad; c.vy = -Math.abs(c.vy)*0.5; }
    }
  }
}

/* ════════════════════════════════════════════════════════════════════
   RENDERER
   ════════════════════════════════════════════════════════════════════ */

function colorForS(s) {
  // cyan (organized) → green → amber → red (chaotic)
  if (s >= 0.55) return { fill: '#50ddff', ring: '#8defff', glow: 'rgba(80,221,255,0.45)' };
  if (s >= 0.25) return { fill: '#58d78a', ring: '#7fe6a5', glow: 'rgba(88,215,138,0.35)' };
  if (s >= 0.08) return { fill: '#ffb347', ring: '#ffd08a', glow: 'rgba(255,179,71,0.30)' };
  return { fill: '#e45759', ring: '#ff8e90', glow: 'rgba(228,87,89,0.30)' };
}

export function drawWorld(ctx, world) {
  const { width, height } = world;
  ctx.clearRect(0, 0, width, height);

  // subtle grid
  ctx.strokeStyle = 'rgba(38,54,86,0.25)';
  ctx.lineWidth = 1;
  const step = 40;
  for (let x = 0; x < width; x += step) { ctx.beginPath(); ctx.moveTo(x,0); ctx.lineTo(x,height); ctx.stroke(); }
  for (let y = 0; y < height; y += step) { ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(width,y); ctx.stroke(); }

  // cells
  for (const c of world.cells) {
    const col = colorForS(c.pattern_s);
    const r = c.radius * 1.8;  // visual scale

    // glow
    const grad = ctx.createRadialGradient(c.x, c.y, r*0.2, c.x, c.y, r*1.8);
    grad.addColorStop(0, col.glow);
    grad.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = grad;
    ctx.beginPath(); ctx.arc(c.x, c.y, r*1.8, 0, 2*Math.PI); ctx.fill();

    // membrane body
    ctx.fillStyle = 'rgba(11,18,32,0.85)';
    ctx.strokeStyle = col.ring;
    ctx.lineWidth = 1.2;
    ctx.beginPath(); ctx.arc(c.x, c.y, r, 0, 2*Math.PI); ctx.fill(); ctx.stroke();

    // RD pattern ring — 24 nodes colored by v
    const innerR = r * 0.76, outerR = r * 0.98;
    for (let i = 0; i < N_NODES; i++) {
      const a0 = (i / N_NODES) * 2 * Math.PI - Math.PI/2;
      const a1 = ((i+1) / N_NODES) * 2 * Math.PI - Math.PI/2;
      const vv = clamp(c.v[i], 0, 1);
      const uu = clamp(c.u[i], 0, 2);
      // color: v-dominant = col.fill, u-dominant = dark
      const intensity = clamp(vv * 1.8, 0, 1);
      ctx.fillStyle = blendColor('#0b1220', col.fill, intensity);
      ctx.beginPath();
      ctx.arc(c.x, c.y, outerR, a0, a1);
      ctx.arc(c.x, c.y, innerR, a1, a0, true);
      ctx.closePath();
      ctx.fill();
    }

    // central S dot
    const coreAlpha = clamp(c.pattern_s, 0, 1);
    if (coreAlpha > 0.05) {
      ctx.fillStyle = col.fill;
      ctx.globalAlpha = coreAlpha * 0.6;
      ctx.beginPath(); ctx.arc(c.x, c.y, r*0.35, 0, 2*Math.PI); ctx.fill();
      ctx.globalAlpha = 1;
    }

    // generation tick marks (small, subtle) at top
    if (c.generation > 0) {
      ctx.fillStyle = 'rgba(255,255,255,0.5)';
      ctx.font = '9px JetBrains Mono, monospace';
      ctx.textAlign = 'center';
      ctx.fillText('G' + c.generation, c.x, c.y - r - 4);
    }
  }
}

function hexToRgb(h) {
  h = h.replace('#','');
  return [parseInt(h.slice(0,2),16), parseInt(h.slice(2,4),16), parseInt(h.slice(4,6),16)];
}
function blendColor(a, b, t) {
  const ra = hexToRgb(a), rb = hexToRgb(b);
  const r = Math.round(ra[0]*(1-t) + rb[0]*t);
  const g = Math.round(ra[1]*(1-t) + rb[1]*t);
  const bl = Math.round(ra[2]*(1-t) + rb[2]*t);
  return `rgb(${r},${g},${bl})`;
}

/* ─── sparkline renderer ─── */
export function drawSpark(canvas, data, opts = {}) {
  const ctx = canvas.getContext('2d');
  const w = canvas.width, h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  if (!data || data.length < 2) return;

  let min = opts.min !== undefined ? opts.min : Infinity;
  let max = opts.max !== undefined ? opts.max : -Infinity;
  if (opts.min === undefined || opts.max === undefined) {
    for (const x of data) { if (x < min) min = x; if (x > max) max = x; }
  }
  if (max <= min) max = min + 1;
  const pad = 4;

  // area fill
  const col = opts.color || '#50ddff';
  ctx.beginPath();
  for (let i = 0; i < data.length; i++) {
    const x = pad + (w - 2*pad) * (i / (data.length - 1));
    const y = h - pad - (h - 2*pad) * ((data[i] - min) / (max - min));
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  }
  const fillGrad = ctx.createLinearGradient(0, 0, 0, h);
  fillGrad.addColorStop(0, col + '55');
  fillGrad.addColorStop(1, col + '08');
  ctx.strokeStyle = col;
  ctx.lineWidth = 1.4;
  ctx.stroke();

  ctx.lineTo(w - pad, h - pad);
  ctx.lineTo(pad, h - pad);
  ctx.closePath();
  ctx.fillStyle = fillGrad;
  ctx.fill();

  // threshold guide
  if (opts.threshold !== undefined) {
    const ty = h - pad - (h - 2*pad) * ((opts.threshold - min) / (max - min));
    ctx.strokeStyle = 'rgba(214,228,255,0.25)';
    ctx.setLineDash([2,3]); ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(pad, ty); ctx.lineTo(w-pad, ty); ctx.stroke();
    ctx.setLineDash([]);
  }

  // last-value marker
  const last = data[data.length - 1];
  const lx = w - pad;
  const ly = h - pad - (h - 2*pad) * ((last - min) / (max - min));
  ctx.fillStyle = col;
  ctx.beginPath(); ctx.arc(lx, ly, 2.2, 0, 2*Math.PI); ctx.fill();
}
