/* ════════════════════════════════════════════════════════════════════
   GENESIS ENGINE — Icosphere + Laplace-Beltrami (browser port)

   Ports mesh_utils.py to pure JS.  Icosahedron seed, Loop subdivision
   with midpoint caching, barycentric vertex area (mass matrix diagonal),
   and cotangent-weight Laplace-Beltrami as a compressed sparse structure
   you can apply with a single `laplaceApply(u, out)` call.

   Subdivision 3 → 642 verts / 1280 faces / ~4482 nonzeros.  Built once
   at module load and frozen; every Cell2D shares the same mesh.
   ════════════════════════════════════════════════════════════════════ */

/* ─── math helpers ─── */
const norm3 = (x, y, z) => Math.hypot(x, y, z);
function normalize([x, y, z]) {
  const n = norm3(x, y, z) || 1;
  return [x / n, y / n, z / n];
}
function sub([a, b, c], [d, e, f]) { return [a - d, b - e, c - f]; }
function cross([a, b, c], [d, e, f]) {
  return [b * f - c * e, c * d - a * f, a * e - b * d];
}
function dot([a, b, c], [d, e, f]) { return a * d + b * e + c * f; }

/* ─── icosahedron seed (12 verts, 20 faces) ─── */
function icosahedron() {
  const phi = (1 + Math.sqrt(5)) / 2;
  const raw = [
    [-1,  phi,  0], [ 1,  phi,  0], [-1, -phi,  0], [ 1, -phi,  0],
    [ 0, -1,  phi], [ 0,  1,  phi], [ 0, -1, -phi], [ 0,  1, -phi],
    [ phi,  0, -1], [ phi,  0,  1], [-phi,  0, -1], [-phi,  0,  1],
  ].map(normalize);
  const faces = [
    [ 0,11, 5], [ 0, 5, 1], [ 0, 1, 7], [ 0, 7,10], [ 0,10,11],
    [ 1, 5, 9], [ 5,11, 4], [11,10, 2], [10, 7, 6], [ 7, 1, 8],
    [ 3, 9, 4], [ 3, 4, 2], [ 3, 2, 6], [ 3, 6, 8], [ 3, 8, 9],
    [ 4, 9, 5], [ 2, 4,11], [ 6, 2,10], [ 8, 6, 7], [ 9, 8, 1],
  ];
  return { verts: raw, faces };
}

/* ─── Loop subdivision projected onto the unit sphere ─── */
function subdivide({ verts, faces }) {
  const next = verts.map(v => v.slice());
  const cache = new Map();
  const midpoint = (a, b) => {
    const key = a < b ? `${a}|${b}` : `${b}|${a}`;
    const hit = cache.get(key);
    if (hit !== undefined) return hit;
    const va = next[a], vb = next[b];
    const m = normalize([va[0] + vb[0], va[1] + vb[1], va[2] + vb[2]]);
    const idx = next.length;
    next.push(m);
    cache.set(key, idx);
    return idx;
  };
  const newFaces = [];
  for (const [a, b, c] of faces) {
    const ab = midpoint(a, b);
    const bc = midpoint(b, c);
    const ca = midpoint(c, a);
    newFaces.push([a, ab, ca], [b, bc, ab], [c, ca, bc], [ab, bc, ca]);
  }
  return { verts: next, faces: newFaces };
}

export function icosphere(subdivisions = 3) {
  let m = icosahedron();
  for (let i = 0; i < subdivisions; i++) m = subdivide(m);
  return m;
}

/* ─── face / vertex adjacency ─── */
function faceAdjacency(nVerts, faces) {
  const adj = Array.from({ length: nVerts }, () => new Set());
  for (const [a, b, c] of faces) {
    adj[a].add(b); adj[a].add(c);
    adj[b].add(a); adj[b].add(c);
    adj[c].add(a); adj[c].add(b);
  }
  return adj.map(s => Array.from(s).sort((x, y) => x - y));
}

/* ─── barycentric vertex area ─── */
function vertexAreas(verts, faces) {
  const A = new Float64Array(verts.length);
  for (const [a, b, c] of faces) {
    const va = verts[a], vb = verts[b], vc = verts[c];
    const e1 = sub(vb, va), e2 = sub(vc, va);
    const faceArea = 0.5 * norm3(...cross(e1, e2));
    A[a] += faceArea / 3;
    A[b] += faceArea / 3;
    A[c] += faceArea / 3;
  }
  return A;
}

/* ─── cotangent-weight Laplacian in CSR-ish form ────────────────────
   For each vertex i, we store:
     adj[i]  = [j0, j1, ...]     neighbor indices
     w[i]    = [w0, w1, ...]     off-diagonal weights (already summed
                                  across all incident triangles)
     diag[i] = -Σ w[i]           so L u |_i = diag[i]·u[i] + Σ w[i,j]·u[j]
     M[i]    = vertex area       so (Δ u)_i = (L u)_i / M[i]
   Build sparsely: accumulate per-edge contributions from the two
   adjacent triangles as in mesh_utils.cotangent_weights.                 */
function buildCotangentLaplacian(verts, faces) {
  const N = verts.length;
  // edge map: "i|j" (i<j) -> accumulated weight (sum of half-cotangents)
  const edgeW = new Map();
  const add = (i, j, w) => {
    const key = i < j ? `${i}|${j}` : `${j}|${i}`;
    edgeW.set(key, (edgeW.get(key) || 0) + w);
  };

  for (const [i, j, k] of faces) {
    const vi = verts[i], vj = verts[j], vk = verts[k];
    const cotAt = (apex, a, b) => {
      const u = sub(a, apex), v = sub(b, apex);
      const d = dot(u, v);
      const c = norm3(...cross(u, v));
      return d / Math.max(c, 1e-12);
    };
    const cotI = cotAt(vi, vj, vk);   // edge (j,k)
    const cotJ = cotAt(vj, vk, vi);   // edge (k,i)
    const cotK = cotAt(vk, vi, vj);   // edge (i,j)
    add(j, k, 0.5 * cotI);
    add(k, i, 0.5 * cotJ);
    add(i, j, 0.5 * cotK);
  }

  // invert to per-vertex neighbor+weight arrays
  const adj = Array.from({ length: N }, () => []);
  const w = Array.from({ length: N }, () => []);
  for (const [key, val] of edgeW) {
    const [aS, bS] = key.split('|');
    const a = +aS, b = +bS;
    adj[a].push(b); w[a].push(val);
    adj[b].push(a); w[b].push(val);
  }
  // freeze to Int32Array / Float64Array per-row and build a flat index
  const rowStart = new Int32Array(N + 1);
  let total = 0;
  for (let i = 0; i < N; i++) { rowStart[i] = total; total += adj[i].length; }
  rowStart[N] = total;
  const colIdx = new Int32Array(total);
  const weight = new Float64Array(total);
  const diag = new Float64Array(N);
  for (let i = 0, p = 0; i < N; i++) {
    let s = 0;
    for (let q = 0; q < adj[i].length; q++, p++) {
      colIdx[p] = adj[i][q];
      weight[p] = w[i][q];
      s += w[i][q];
    }
    diag[i] = -s;  // L_ii = -Σ off-diagonals
  }
  return { rowStart, colIdx, weight, diag, nnz: total };
}

/* ─── module-level singleton: build once ───────────────────────────── */
const _m = icosphere(3);
export const VERTS = _m.verts.map(v => v.slice());         // 642 × [x,y,z]
export const FACES = _m.faces.map(f => f.slice());         // 1280 × [a,b,c]
export const N_VERTS = VERTS.length;
export const FACE_ADJ = faceAdjacency(N_VERTS, FACES);
export const MASS = vertexAreas(VERTS, FACES);             // Float64Array(642)
const _lap = buildCotangentLaplacian(VERTS, FACES);
export const L_ROW_START = _lap.rowStart;
export const L_COL_IDX   = _lap.colIdx;
export const L_WEIGHT    = _lap.weight;
export const L_DIAG      = _lap.diag;
export const L_NNZ       = _lap.nnz;

/* ─── apply Laplace-Beltrami:  out[i] = (Δ u)_i = (L u)_i / M[i] ─── */
export function laplaceApply(u, out) {
  const N = N_VERTS;
  const rs = L_ROW_START, ci = L_COL_IDX, w = L_WEIGHT, d = L_DIAG;
  const M = MASS;
  for (let i = 0; i < N; i++) {
    let acc = d[i] * u[i];
    const end = rs[i + 1];
    for (let p = rs[i]; p < end; p++) acc += w[p] * u[ci[p]];
    out[i] = acc / M[i];
  }
}

/* ─── connected-components of u > mean(u), using FACE_ADJ ───────────── */
export function countComponentsAboveMean(u) {
  const N = N_VERTS;
  let s = 0;
  for (let i = 0; i < N; i++) s += u[i];
  const mean = s / N;
  const visited = new Uint8Array(N);
  const stack = new Int32Array(N);
  let n = 0, top = 0;
  for (let i = 0; i < N; i++) {
    if (visited[i] || u[i] <= mean) continue;
    n++;
    stack[top++] = i;
    visited[i] = 1;
    while (top > 0) {
      const node = stack[--top];
      const nbs = FACE_ADJ[node];
      for (let q = 0; q < nbs.length; q++) {
        const nb = nbs[q];
        if (!visited[nb] && u[nb] > mean) { visited[nb] = 1; stack[top++] = nb; }
      }
    }
  }
  return n;
}
