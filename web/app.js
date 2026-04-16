/* ════════════════════════════════════════════════════════════════════
   GENESIS ENGINE — App controller
   View switching · simulation loop · UI binding
   ════════════════════════════════════════════════════════════════════ */

import { World, drawWorld, drawSpark } from './genesis.js';
import { World2D, drawWorld2D, drawSpark2D } from './genesis_2d.js';

/* ─── view switching ─── */
let sphereInited = false;
document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById('view-' + tab.dataset.view).classList.add('active');
    // Lazy-init the sphere world the first time the SPHERE tab is opened.
    // Cotangent-Laplacian construction is ~30 ms on 642 verts — nothing to
    // hide, but deferring it keeps the initial page-load fast.
    if (tab.dataset.view === 'sphere' && !sphereInited) initSphere();
  });
});

/* ─── simulation setup ─── */
const canvas = document.getElementById('world');
const ctx = canvas.getContext('2d');
const world = new World(canvas.width, canvas.height);

// Debug hooks — exposed so headless capture scripts (e.g. Fig 6 generator)
// can drive the sim directly instead of relying on requestAnimationFrame,
// which is heavily throttled in headless-chromium.
window.__genesis = window.__genesis || {};
window.__genesis.world = world;
window.__genesis.ctx   = ctx;
window.__genesis.drawWorld = drawWorld;
// Batch stepper: runs `n` ticks in a tight loop, then returns
// { tick, phase, B, C, D, pop, S, CV, gen }. Much faster than RAF in
// headless chromium because no paint is scheduled between steps.
window.__genesis.stepN = (n) => {
  for (let i = 0; i < n; i++) world.step();
  const s = world.stats;
  const ph = world.phases;
  return {
    tick: world.tick, phase: s.phase, B: ph.B_tick, C: ph.C_tick, D: ph.D_tick,
    pop: s.pop, S: s.mean_s, CV: s.mean_cv, gen: s.max_gen,
    divisions: world.total_div,
  };
};

let running = true;
let speed = 2;          // ticks per frame
let lastRender = 0;
let afId = null;        // in-flight requestAnimationFrame id (null = paused, no pending frame)

const spCanvases = {
  pop: document.getElementById('sp-pop'),
  s:   document.getElementById('sp-s'),
  cv:  document.getElementById('sp-cv'),
  res: document.getElementById('sp-res'),
};

/* ─── controls ─── */
const btnPlay = document.getElementById('btn-play');
function setRunning(next) {
  // Normalize to bool, set button state, and physically start/stop the RAF
  // chain so there is no chance of a stale closure continuing to step().
  running = !!next;
  btnPlay.textContent = running ? 'PAUSE' : 'PLAY';
  btnPlay.classList.toggle('primary', running);
  if (running) {
    if (afId == null) afId = requestAnimationFrame(loop);
  } else {
    if (afId != null) { cancelAnimationFrame(afId); afId = null; }
    // repaint once so the frozen state is visible
    drawWorld(ctx, world);
    updateUI(true);
  }
}
btnPlay.addEventListener('click', () => setRunning(!running));
document.getElementById('btn-reset').addEventListener('click', () => {
  world.reset();
  updateUI(true);
  setRunning(true);
});
document.querySelectorAll('.btn.sp').forEach(b => {
  b.addEventListener('click', () => {
    speed = parseInt(b.dataset.speed, 10);
    document.querySelectorAll('.btn.sp').forEach(x => x.classList.remove('active'));
    b.classList.add('active');
  });
});

/* ════════════════════════════════════════════════════════════════════
   EXPORTERS — time series · cell snapshot · full bundle
   Parameterized on a world instance so the 2D tab can reuse the same
   code path with its own 642-vertex u/v fields.
   ════════════════════════════════════════════════════════════════════ */

function runProvenanceLines(w, label) {
  const ph = w.phases;
  const cbm = (ph.B_tick > 0 && ph.C_tick > 0)
    ? (ph.B_tick < ph.C_tick)
    : (ph.B_tick > 0 ? true : 'N/A');
  return [
    '# Genesis Engine — live simulation export',
    `# source: web/ in-browser port (${label})`,
    `# exported_at=${new Date().toISOString()}`,
    `# tick=${w.tick}`,
    `# phase=${w.stats.phase}`,
    `# phase_B_tick=${ph.B_tick}`,
    `# phase_C_tick=${ph.C_tick}`,
    `# phase_D_tick=${ph.D_tick}`,
    `# clock_before_map=${cbm}`,
    `# population=${w.stats.pop}`,
    `# mean_s=${w.stats.mean_s.toFixed(4)}`,
    `# mean_cv=${w.stats.mean_cv.toFixed(4)}`,
    `# resource=${w.stats.resource.toFixed(2)}`,
    `# max_gen=${w.stats.max_gen}`,
    `# total_divisions=${w.total_div}`,
  ];
}

function download(text, filename, mime = 'text/csv;charset=utf-8') {
  const blob = new Blob([text], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function timestampSlug() {
  return new Date().toISOString().replace(/[:.]/g,'-').slice(0,19);
}

function fmtNum(v) {
  if (typeof v === 'number') return Number.isInteger(v) ? v : v.toFixed(4);
  return v;
}

/* ─── 1 · TIME SERIES CSV ─── */
function buildTimeSeriesCSV(w, label) {
  const rows = w.history;
  const cols = ['tick','population','mean_s','mean_cv','resource','max_gen','phase','total_divisions'];
  const lines = [...runProvenanceLines(w, label),
    `# rows=${rows.length}`,
    '# columns: ' + cols.join(','),
    cols.join(','),
  ];
  for (const r of rows) lines.push(cols.map(c => fmtNum(r[c])).join(','));
  return lines.join('\n') + '\n';
}

/* ─── 2 · CELL SNAPSHOT CSV ─── */
function buildCellSnapshotCSV(w, label, opts = {}) {
  const cells = w.cells;
  const nNodes = cells.length && cells[0].u ? cells[0].u.length : 0;
  // For large node counts (the 2D icosphere has 642 verts → 1,284 u/v
  // columns), pack u/v as semicolon-joined vectors so the CSV stays
  // human-friendly. The 1D ring stays wide (24 nodes → 48 cols).
  const packVectors = opts.packVectors ?? (nNodes > 64);

  const baseCols = [
    'cell_idx', 'generation', 'age', 'radius', 'prev_radius', 'energy',
    'pattern_s', 'last_div_age', 'stab_tick',
    'genome_Da', 'genome_Db', 'genome_f', 'genome_k',
    'division_times', 'x', 'y',
  ];
  let cols;
  const headerNotes = [];
  if (packVectors) {
    cols = [...baseCols, 'u_vector', 'v_vector'];
    headerNotes.push(
      '# u_vector, v_vector are semicolon-joined arrays of length n_nodes',
      '# (packed because the icosphere has 642 vertices)',
    );
  } else {
    const uCols = []; const vCols = [];
    for (let i = 0; i < nNodes; i++) { uCols.push(`u_${i}`); vCols.push(`v_${i}`); }
    cols = [...baseCols, ...uCols, ...vCols];
    headerNotes.push('# u_i, v_i are Gray-Scott concentrations at node i');
  }

  const lines = [...runProvenanceLines(w, label),
    `# cells=${cells.length}`,
    `# n_nodes=${nNodes}`,
    '# division_times is a semicolon-joined list',
    ...headerNotes,
    cols.join(','),
  ];
  cells.forEach((c, i) => {
    const fixed = [
      i, c.generation, c.age, c.radius.toFixed(4), c.prev_radius.toFixed(4),
      c.energy.toFixed(4), c.pattern_s.toFixed(4), c.last_div_age, c.stab_tick,
      c.genome.Da.toFixed(6), c.genome.Db.toFixed(6),
      c.genome.f.toFixed(6), c.genome.k.toFixed(6),
      c.division_times.join(';'),
      c.x.toFixed(2), c.y.toFixed(2),
    ];
    if (packVectors) {
      lines.push([
        ...fixed,
        Array.from(c.u).map(x => x.toFixed(4)).join(';'),
        Array.from(c.v).map(x => x.toFixed(4)).join(';'),
      ].join(','));
    } else {
      lines.push([
        ...fixed,
        ...Array.from(c.u).map(x => x.toFixed(4)),
        ...Array.from(c.v).map(x => x.toFixed(4)),
      ].join(','));
    }
  });
  return lines.join('\n') + '\n';
}

/* ─── 3 · FULL BUNDLE — both CSVs + metadata in a single .txt ─── */
function buildBundle(w, label) {
  const hr = '=' .repeat(78);
  const sec = (t) => `\n${hr}\n== ${t}\n${hr}\n`;
  const parts = [];
  parts.push(hr, `== GENESIS ENGINE · full simulation bundle (${label})`, hr, '');
  parts.push(runProvenanceLines(w, label).join('\n'));
  parts.push(sec('TIME SERIES'));
  parts.push(w.history.length ? buildTimeSeriesCSV(w, label) : '(no samples yet)\n');
  parts.push(sec('CELL SNAPSHOT'));
  parts.push(w.cells.length ? buildCellSnapshotCSV(w, label) : '(population empty)\n');
  parts.push(sec('END'));
  return parts.join('');
}

/* Wire the three buttons for a given world. `slug` is prepended to
   downloaded filenames so 1D and 2D exports don't collide on disk. */
function wireExporters({ btnTs, btnCells, btnBundle, world: w, label, slug }) {
  btnTs.addEventListener('click', () => {
    if (!w.history.length) { alert('No samples yet — let the simulation run for a few ticks first.'); return; }
    download(buildTimeSeriesCSV(w, label), `${slug}_timeseries_${timestampSlug()}.csv`);
  });
  btnCells.addEventListener('click', () => {
    if (!w.cells.length) { alert('Population is empty — nothing to snapshot.'); return; }
    download(buildCellSnapshotCSV(w, label), `${slug}_cells_t${w.tick}_${timestampSlug()}.csv`);
  });
  btnBundle.addEventListener('click', () => {
    if (!w.cells.length && !w.history.length) { alert('No data to export yet.'); return; }
    download(buildBundle(w, label), `${slug}_bundle_t${w.tick}_${timestampSlug()}.txt`, 'text/plain;charset=utf-8');
  });
}

wireExporters({
  btnTs:     document.getElementById('btn-export-ts'),
  btnCells:  document.getElementById('btn-export-cells'),
  btnBundle: document.getElementById('btn-export-bundle'),
  world, label: '1D ring (24-node membrane)', slug: 'genesis_1d',
});

/* ─── UI update ─── */
function fmt(x, d = 3) { if (x === null || x === undefined || isNaN(x)) return '—'; return Number(x).toFixed(d); }
function fmtInt(x) { return (x === null || isNaN(x)) ? '—' : Math.round(x).toString(); }

/* Phase predicate thresholds — kept in sync with genesis.js / genesis_2d.js.
   Only used by the CURRENT STATE panel; detection of latched transitions
   still lives inside each World implementation. */
const P = { B_CV: 0.25, C_S: 0.25, D_S: 0.35, D_CV: 0.30, D_GEN: 5 };

/* live highest-satisfied phase (independent of latched state) */
function liveHighestPhase(cv, s, gen) {
  const liveB = (cv > 0) && (cv < P.B_CV);
  const liveC = liveB && (s > P.C_S);
  const liveD = liveC && (s > P.D_S) && (cv < P.D_CV) && (gen >= P.D_GEN);
  if (liveD) return 'D';
  if (liveC) return 'C';
  if (liveB) return 'B';
  return 'A';
}

/* Render a pair of threshold checks inline, e.g.
     [ B<0.25 ✗ | D<0.30 ✓ ]
   `gates` is [{label, pass}, …]. */
function gateSpans(gates) {
  const parts = gates.map(g =>
    `<span class="${g.pass ? 'ok' : 'bad'}">${g.label} ${g.pass ? '✓' : '✗'}</span>`
  );
  return `[ ${parts.join(' · ')} ]`;
}

/* Update the CURRENT STATE panel for a given tab prefix. `prefix` is
   '' for the 1D tab (ids like cs-cv-v) or '2' for the 2D tab
   (ids like cs2-cv-v). */
function updateCurrentState(prefix, stats) {
  if (stats.pop === 0) {
    // extinct → nothing to evaluate
    const badge = document.getElementById(`cs${prefix}-badge`);
    badge.textContent = '—';
    badge.setAttribute('data-phase', 'A');
    document.getElementById(`cs${prefix}-cv-v`).textContent  = '—';
    document.getElementById(`cs${prefix}-s-v`).textContent   = '—';
    document.getElementById(`cs${prefix}-gen-v`).textContent = '—';
    document.getElementById(`cs${prefix}-cv-gate`).innerHTML  = '';
    document.getElementById(`cs${prefix}-s-gate`).innerHTML   = '';
    document.getElementById(`cs${prefix}-gen-gate`).innerHTML = '';
    return;
  }
  const cv = stats.mean_cv, s = stats.mean_s, gen = stats.max_gen;
  const live = liveHighestPhase(cv, s, gen);

  const badge = document.getElementById(`cs${prefix}-badge`);
  badge.textContent = live;
  badge.setAttribute('data-phase', live);

  document.getElementById(`cs${prefix}-cv-v`).textContent  = cv.toFixed(3);
  document.getElementById(`cs${prefix}-s-v`).textContent   = s.toFixed(3);
  document.getElementById(`cs${prefix}-gen-v`).textContent = gen;

  document.getElementById(`cs${prefix}-cv-gate`).innerHTML = gateSpans([
    { label: `B<${P.B_CV}`, pass: cv > 0 && cv < P.B_CV },
    { label: `D<${P.D_CV.toFixed(2)}`, pass: cv > 0 && cv < P.D_CV },
  ]);
  document.getElementById(`cs${prefix}-s-gate`).innerHTML = gateSpans([
    { label: `C>${P.C_S}`, pass: s > P.C_S },
    { label: `D>${P.D_S}`, pass: s > P.D_S },
  ]);
  document.getElementById(`cs${prefix}-gen-gate`).innerHTML = gateSpans([
    { label: `D≥${P.D_GEN}`, pass: gen >= P.D_GEN },
  ]);
}

function updateUI(force = false) {
  const s = world.stats;
  document.getElementById('s-pop').textContent = s.pop;
  document.getElementById('s-res').textContent = fmt(s.resource, 0);
  document.getElementById('s-s').textContent   = fmt(s.mean_s, 3);
  document.getElementById('s-cv').textContent  = fmt(s.mean_cv, 3);
  document.getElementById('s-div').textContent = world.total_div;
  document.getElementById('s-gen').textContent = s.max_gen;

  document.getElementById('o-tick').textContent  = world.tick.toLocaleString();
  document.getElementById('o-phase').textContent = s.phase;

  // phase overlay highlighting
  const ph = world.phases;
  const rows = ['A','B','C','D'];
  for (const p of rows) {
    const row = document.querySelector('.phase-row:nth-child(' + (rows.indexOf(p)+1) + ')');
    const reached = p === 'A' ? true : ph[p];
    row.classList.toggle('reached', !!reached);
    row.classList.toggle('current', s.phase === p);
  }

  document.getElementById('ev-B').textContent = ph.B_tick > 0 ? 't = ' + ph.B_tick.toLocaleString() : '—';
  document.getElementById('ev-C').textContent = ph.C_tick > 0 ? 't = ' + ph.C_tick.toLocaleString() : '—';
  document.getElementById('ev-D').textContent = ph.D_tick > 0 ? 't = ' + ph.D_tick.toLocaleString() : '—';

  updateCurrentState('', s);

  // sparklines
  drawSpark(spCanvases.pop, world.spark.pop, { color:'#50ddff', min:0 });
  drawSpark(spCanvases.s,   world.spark.s,   { color:'#58d78a', min:0, max:1, threshold: 0.25 });
  drawSpark(spCanvases.cv,  world.spark.cv,  { color:'#b08bff', min:0, max:1, threshold: 0.25 });
  drawSpark(spCanvases.res, world.spark.res, { color:'#ffb347', min:0, max:100 });
}

/* ─── main loop ─── */
function loop(t) {
  // If we ever re-enter after a cancel, just drop the frame.
  if (!running) { afId = null; return; }
  for (let i = 0; i < speed; i++) world.step();
  drawWorld(ctx, world);
  if (t - lastRender > 100) { updateUI(); lastRender = t; }
  afId = requestAnimationFrame(loop);
}

updateUI(true);
afId = requestAnimationFrame(loop);

/* ════════════════════════════════════════════════════════════════════
   2D SPHERE VIEW  —  lazy-initialized on first tab activation
   ════════════════════════════════════════════════════════════════════ */

let world2d = null;
let ctx2d = null;
let running2d = true;
let speed2d = 2;
let lastRender2d = 0;
let afId2d = null;

const sp2Canvases = {
  pop: () => document.getElementById('sp2-pop'),
  s:   () => document.getElementById('sp2-s'),
  cv:  () => document.getElementById('sp2-cv'),
  res: () => document.getElementById('sp2-res'),
};

function initSphere() {
  const canvas = document.getElementById('world2d');
  ctx2d = canvas.getContext('2d');
  world2d = new World2D(canvas.width, canvas.height);
  sphereInited = true;

  // debug hooks for headless capture
  window.__genesis = window.__genesis || {};
  window.__genesis.world2d = world2d;
  window.__genesis.ctx2d   = ctx2d;
  window.__genesis.drawWorld2D = drawWorld2D;
  window.__genesis.redraw2d = () => drawWorld2D(ctx2d, world2d);

  // controls
  const play = document.getElementById('btn2-play');
  function setRunning2d(next) {
    running2d = !!next;
    play.textContent = running2d ? 'PAUSE' : 'PLAY';
    play.classList.toggle('primary', running2d);
    if (running2d) {
      if (afId2d == null) afId2d = requestAnimationFrame(loop2d);
    } else {
      if (afId2d != null) { cancelAnimationFrame(afId2d); afId2d = null; }
      if (world2d && ctx2d) drawWorld2D(ctx2d, world2d);
      updateUI2d(true);
    }
  }
  play.addEventListener('click', () => setRunning2d(!running2d));
  document.getElementById('btn2-reset').addEventListener('click', () => {
    world2d.reset();
    updateUI2d(true);
    setRunning2d(true);
  });
  document.querySelectorAll('.btn.sp2').forEach(b => {
    b.addEventListener('click', () => {
      speed2d = parseInt(b.dataset.speed, 10);
      document.querySelectorAll('.btn.sp2').forEach(x => x.classList.remove('active'));
      b.classList.add('active');
    });
  });

  // export buttons — same CSV schema as 1D, packed u/v vectors for the
  // 642-vertex icosphere fields
  wireExporters({
    btnTs:     document.getElementById('btn2-export-ts'),
    btnCells:  document.getElementById('btn2-export-cells'),
    btnBundle: document.getElementById('btn2-export-bundle'),
    world: world2d, label: '2D icosphere (642-vertex membrane)', slug: 'genesis_2d',
  });

  updateUI2d(true);
  afId2d = requestAnimationFrame(loop2d);
}

function updateUI2d() {
  const s = world2d.stats;
  document.getElementById('s2-pop').textContent = s.pop;
  document.getElementById('s2-res').textContent = fmt(s.resource, 0);
  document.getElementById('s2-s').textContent   = fmt(s.mean_s, 3);
  document.getElementById('s2-cv').textContent  = fmt(s.mean_cv, 3);
  document.getElementById('s2-div').textContent = world2d.total_div;
  document.getElementById('s2-gen').textContent = s.max_gen;

  document.getElementById('o2-tick').textContent  = world2d.tick.toLocaleString();
  document.getElementById('o2-phase').textContent = s.phase;

  const ph = world2d.phases;
  const rows = ['A', 'B', 'C', 'D'];
  const rowNodes = document.querySelectorAll('#view-sphere .phase-row');
  for (let i = 0; i < rows.length; i++) {
    const p = rows[i];
    const reached = p === 'A' ? true : ph[p];
    const row = rowNodes[i];
    if (!row) continue;
    row.classList.toggle('reached', !!reached);
    row.classList.toggle('current', s.phase === p);
  }

  document.getElementById('ev2-B').textContent = ph.B_tick > 0 ? 't = ' + ph.B_tick.toLocaleString() : '—';
  document.getElementById('ev2-C').textContent = ph.C_tick > 0 ? 't = ' + ph.C_tick.toLocaleString() : '—';
  document.getElementById('ev2-D').textContent = ph.D_tick > 0 ? 't = ' + ph.D_tick.toLocaleString() : '—';

  updateCurrentState('2', s);

  drawSpark2D(sp2Canvases.pop(), world2d.spark.pop, { color:'#50ddff', min:0 });
  drawSpark2D(sp2Canvases.s(),   world2d.spark.s,   { color:'#58d78a', min:0, max:1, threshold: 0.25 });
  drawSpark2D(sp2Canvases.cv(),  world2d.spark.cv,  { color:'#b08bff', min:0, max:1, threshold: 0.25 });
  drawSpark2D(sp2Canvases.res(), world2d.spark.res, { color:'#ffb347', min:0, max:100 });
}

function loop2d(t) {
  if (!running2d || !world2d) { afId2d = null; return; }
  for (let i = 0; i < speed2d; i++) world2d.step();
  if (ctx2d) drawWorld2D(ctx2d, world2d);
  if (t - lastRender2d > 150) { updateUI2d(); lastRender2d = t; }
  afId2d = requestAnimationFrame(loop2d);
}
