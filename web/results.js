/* ════════════════════════════════════════════════════════════════════
   GENESIS ENGINE — Monte Carlo results view
   Loads results/summary.csv and computes/displays aggregate stats.
   ════════════════════════════════════════════════════════════════════ */

/* ─── CSV parser (minimal, handles our format) ─── */
function parseCSV(text) {
  const lines = text.trim().split(/\r?\n/);
  const header = lines[0].split(',');
  const rows = lines.slice(1).map(line => {
    const cols = line.split(',');
    const row = {};
    for (let i = 0; i < header.length; i++) row[header[i]] = cols[i];
    return row;
  });
  return { header, rows };
}

function num(x) { const n = parseFloat(x); return isNaN(n) ? null : n; }
function toInt(x) { const n = parseInt(x, 10); return isNaN(n) ? null : n; }

function mean(a) { if (!a.length) return NaN; let s=0; for (const x of a) s+=x; return s/a.length; }
function median(a) {
  if (!a.length) return NaN;
  const s = [...a].sort((x,y)=>x-y);
  const m = Math.floor(s.length/2);
  return s.length % 2 ? s[m] : (s[m-1] + s[m]) / 2;
}

/* ─── load and render ─── */
async function loadResults() {
  const metaBox = document.getElementById('meta-box');
  try {
    const res = await fetch('results/summary.csv', { cache: 'no-store' });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const text = await res.text();
    const { rows } = parseCSV(text);
    renderFromRows(rows);
    metaBox.textContent = `source: results/summary.csv · ${rows.length} runs loaded`;
  } catch (err) {
    metaBox.textContent = `Could not load results/summary.csv (${err.message}). Showing hard-coded values from the N=500 run.`;
  }
}

function renderFromRows(rows) {
  const N = rows.length;

  // phase distribution
  const counts = { A:0, B:0, C:0, D:0 };
  for (const r of rows) { const p = r.final_phase; if (counts[p] !== undefined) counts[p]++; }
  const tbody = document.getElementById('phase-tbody');
  tbody.innerHTML = '';
  const labels = { A:'A · Prebiotic', B:'B · Clock', C:'C · Map', D:'D · Agency' };
  for (const p of ['A','B','C','D']) {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${labels[p]}</td><td>${counts[p]}</td><td>${(100*counts[p]/N).toFixed(1)}%</td>`;
    tbody.appendChild(tr);
  }

  // transition times
  const B = rows.map(r => toInt(r.phase_B_tick)).filter(x => x !== null && x > 0);
  const C = rows.map(r => toInt(r.phase_C_tick)).filter(x => x !== null && x > 0);
  const D = rows.map(r => toInt(r.phase_D_tick)).filter(x => x !== null && x > 0);

  const setRow = (prefix, arr) => {
    document.getElementById(`tr-${prefix}mean`).textContent = arr.length ? Math.round(mean(arr)).toLocaleString() : '—';
    document.getElementById(`tr-${prefix}med`).textContent  = arr.length ? Math.round(median(arr)).toLocaleString() : '—';
    document.getElementById(`tr-${prefix}n`).textContent    = `${arr.length}/${N} (${(100*arr.length/N).toFixed(1)}%)`;
  };
  setRow('B', B); setRow('C', C); setRow('D', D);

  // Clock-before-Map — recompute from data as sanity check
  let bbc = 0, cbb = 0, both = 0;
  for (const r of rows) {
    const b = toInt(r.phase_B_tick), c = toInt(r.phase_C_tick);
    if (b > 0 && c > 0) { both++; if (b < c) bbc++; else if (c < b) cbb++; }
  }
  const pct = both > 0 ? (100 * bbc / both) : 0;
  // update the headline if numbers differ from the hard-coded ones
  if (both > 0) {
    document.querySelector('.headline-num').innerHTML = `${pct.toFixed(0)}<span class="pct">%</span>`;
    document.querySelector('.headline-text .hl').textContent = `${bbc} / ${both}`;
    document.querySelector('.headline-text .muted').textContent =
      `N = ${N} independent seeds · ${rows[0] ? (parseInt(rows[0].max_ticks).toLocaleString() + ' ticks each') : ''}`;
  }

  // final-state means
  const finalS = rows.map(r => num(r.final_mean_s)).filter(x => x !== null);
  const finalCV = rows.map(r => num(r.final_mean_cv)).filter(x => x !== null);

  // organized vs disorganized (Hedges' g)
  const org  = rows.filter(r => num(r.final_mean_s) > 0.3);
  const dis  = rows.filter(r => num(r.final_mean_s) < 0.1);
  if (org.length && dis.length) {
    const popOrg = org.map(r => toInt(r.final_pop));
    const popDis = dis.map(r => toInt(r.final_pop));
    const m1 = mean(popOrg), m2 = mean(popDis);
    const sd = (a, m) => { let v=0; for (const x of a) v+=(x-m)*(x-m); return Math.sqrt(v/(a.length-1 || 1)); };
    const s1 = sd(popOrg, m1), s2 = sd(popDis, m2);
    const n1 = popOrg.length, n2 = popDis.length;
    const sp = Math.sqrt(((n1-1)*s1*s1 + (n2-1)*s2*s2) / (n1+n2-2));
    const d  = (m1 - m2) / (sp || 1);
    const J  = 1 - 3 / (4*(n1+n2) - 9);
    const g  = d * J;
    document.getElementById('kpi-g').textContent = g.toFixed(2);
  }
}

loadResults();

/* ─── ablation results (lazy: only if CSV exists) ─── */
async function loadAblations() {
  const section = document.getElementById('ablation-section');
  try {
    const res = await fetch('results/ablations/ablation_summary.csv', { cache: 'no-store' });
    if (!res.ok) return;    // no ablation run yet
    const text = await res.text();
    const { rows } = parseCSV(text);
    if (!rows.length) return;
    renderAblations(rows);
    section.classList.remove('hidden');
  } catch {
    /* silent — ablation section stays hidden */
  }
}

function renderAblations(rows) {
  // group by parameter, then sort each group by value
  const groups = {};
  for (const r of rows) {
    if (!groups[r.parameter]) groups[r.parameter] = [];
    groups[r.parameter].push({
      value:        parseFloat(r.value),
      is_baseline:  r.is_baseline === 'True' || r.is_baseline === 'true',
      n_runs:       toInt(r.n_runs),
      n_both:       toInt(r.n_reached_both),
      cbm_count:    toInt(r.clock_before_map_count),
      cbm_pct:      num(r.clock_before_map_pct),
      mean_delay:   num(r.mean_delay),
    });
  }
  const order = ['LIPID_SUPPLY', 'RD_NOISE', 'GROWTH_PERTURB', 'STAB_WINDOW'];
  const tbody = document.getElementById('ablation-tbody');
  tbody.innerHTML = '';

  let allPass = true, totalCbm = 0, totalBoth = 0, totalConditions = 0;

  for (const param of order) {
    const g = groups[param];
    if (!g) continue;
    g.sort((a,b) => a.value - b.value);   // low, baseline, high (for our sweeps)

    const tr = document.createElement('tr');
    const paramCell = document.createElement('td');
    paramCell.textContent = param;
    tr.appendChild(paramCell);

    let rowPass = true;
    for (const cell of g) {
      const td = document.createElement('td');
      totalConditions++;
      if (cell.n_both > 0) {
        totalCbm += cell.cbm_count;
        totalBoth += cell.n_both;
        const pct = cell.cbm_pct.toFixed(0);
        td.innerHTML = `<span class="big">${cell.cbm_count}/${cell.n_both}</span><span class="sub">v=${cell.value} · ${pct}%</span>`;
        if (cell.cbm_pct >= 100) {
          td.classList.add(cell.is_baseline ? 'pass-star' : 'pass');
        } else {
          td.classList.add('fail');
          rowPass = false;
        }
      } else {
        td.innerHTML = `<span class="big">—</span><span class="sub">v=${cell.value} · N/A</span>`;
      }
      if (cell.is_baseline) td.classList.add('baseline');
      tr.appendChild(td);
    }

    const verdict = document.createElement('td');
    verdict.textContent = rowPass ? '✓' : '✗';
    verdict.className = rowPass ? 'pass' : 'fail';
    verdict.style.fontSize = '18px';
    tr.appendChild(verdict);
    if (!rowPass) allPass = false;

    tbody.appendChild(tr);
  }

  document.getElementById('ablation-subtitle').innerHTML =
    `One parameter varied at a time; all others held at baseline. ` +
    `N=${rows[0].n_runs} runs × ${totalConditions} conditions = ${rows[0].n_runs * totalConditions} additional simulations.`;

  const footEl = document.getElementById('ablation-foot');
  if (allPass && totalBoth > 0) {
    footEl.innerHTML = `<span class="tag">✓ ROBUST</span> — Clock → Map ordering held in ${totalCbm} / ${totalBoth} runs across all ${totalConditions} parameter conditions (${(100*totalCbm/totalBoth).toFixed(1)}%).`;
  } else if (totalBoth > 0) {
    footEl.innerHTML = `Partial pass — ${totalCbm} / ${totalBoth} runs across ${totalConditions} conditions (${(100*totalCbm/totalBoth).toFixed(1)}%). See failing cells.`;
  }
}

loadAblations();

/* ─── Background Jobs — polls /api/status ─────────────────────────────
 * In local mode (./start.sh launches server.py) this endpoint reports on
 * running Monte Carlo / ablation workers. On a static host (Cloudflare
 * Pages, GitHub Pages) the endpoint does not exist — we detect the first
 * failure, render a one-time static-mode notice, and stop polling.
 * --------------------------------------------------------------------- */
let __jobsStaticMode = false;

async function loadJobs() {
  const list = document.getElementById('jobs-list');
  const stamp = document.getElementById('jobs-stamp');
  if (!list || __jobsStaticMode) return;
  try {
    const res = await fetch('/api/status', { cache: 'no-store' });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const data = await res.json();
    renderJobs(data, list, stamp);
  } catch (err) {
    __jobsStaticMode = true;
    if (__jobsPoller) { clearInterval(__jobsPoller); __jobsPoller = null; }
    list.innerHTML = `
      <div class="job-row static-mode">
        <span class="job-name">Static deployment — live job status disabled</span>
        <span class="job-status idle">offline</span>
        <span class="job-detail">
          The <code>/api/status</code> endpoint requires the local Python server.
          To monitor running Monte Carlo and ablation jobs, clone the repo and
          launch with <code>./start.sh</code>.
          See <a href="https://github.com/Ouroboros-Research-Institute/genesis-engine#quickstart" target="_blank" rel="noopener">the README</a>
          for setup.
        </span>
      </div>`;
    stamp.textContent = 'static mode — showing published Monte Carlo results only';
  }
}

function jobStatusClass(s) {
  if (!s) return '';
  if (s.startsWith('running')) return 'running';
  if (s.startsWith('complete')) return 'done';
  if (s === 'partial') return 'partial';
  return 'idle';
}

function renderJobs(data, list, stamp) {
  list.innerHTML = '';
  for (const j of data.jobs) {
    const row = document.createElement('div');
    row.className = 'job-row';
    const bits = [];

    if (j.name.includes('self-test')) {
      if (j.B_tick != null) bits.push(`B=${j.B_tick}`);
      if (j.C_tick != null) bits.push(`C=${j.C_tick}`);
      if (j.D_tick != null && j.D_tick > 0) bits.push(`D=${j.D_tick}`);
      if (j.final_phase) bits.push(`final=${j.final_phase}`);
      else if (j.current_phase) bits.push(`phase=${j.current_phase}`);
    } else if (j.name.startsWith('Ablation')) {
      bits.push(`${j.conditions_done}/${j.conditions_total} conditions`);
    } else {
      // monte carlo-style
      if (j.runs_total != null) bits.push(`${j.runs_done}/${j.runs_total} runs`);
      else if (j.runs_done) bits.push(`${j.runs_done} runs`);
    }

    const cls = jobStatusClass(j.status);
    row.innerHTML = `
      <span class="job-name">${j.name}</span>
      <span class="job-status ${cls}">${j.status}</span>
      <span class="job-detail">${bits.join(' · ') || '—'}</span>
    `;
    list.appendChild(row);
  }
  stamp.textContent = `updated ${new Date(data.timestamp).toLocaleTimeString()}`;
}

let __jobsPoller = null;
loadJobs();
__jobsPoller = setInterval(loadJobs, 5000);
