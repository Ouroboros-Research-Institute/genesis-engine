"""
mesh_utils.py — Icosphere mesh + Laplace-Beltrami operator for Genesis Engine 2D.

Stage 1 of the 2D upgrade. Does not touch the 1D code.

Public API
----------
icosphere(subdivisions=2)           -> (vertices, faces)  unit sphere triangulation
vertex_areas(vertices, faces)        -> 1D array of per-vertex barycentric areas
cotangent_weights(vertices, faces)   -> (L, M) sparse cotangent matrix + mass diag
laplace_beltrami(vertices, faces)    -> sparse Δ = M^(-1) L  (THE operator used in RD)
face_adjacency(n_verts, faces)       -> list[list[int]]   per-vertex neighbor lists
verify_spectrum(Δ, k=20)             -> prints ℓ(ℓ+1) comparison, returns bool pass
"""

from __future__ import annotations

import numpy as np
from scipy.sparse import csr_matrix, coo_matrix, diags
from scipy.linalg import eigh


# ─────────────────────────── icosahedron seed ───────────────────────────
def _icosahedron():
    """12-vertex regular icosahedron on the unit sphere + 20 faces."""
    phi = (1.0 + np.sqrt(5.0)) / 2.0
    v = np.array([
        [-1,  phi,  0], [ 1,  phi,  0], [-1, -phi,  0], [ 1, -phi,  0],
        [ 0, -1,  phi], [ 0,  1,  phi], [ 0, -1, -phi], [ 0,  1, -phi],
        [ phi,  0, -1], [ phi,  0,  1], [-phi,  0, -1], [-phi,  0,  1],
    ], dtype=np.float64)
    v /= np.linalg.norm(v, axis=1, keepdims=True)
    f = np.array([
        [ 0,11, 5], [ 0, 5, 1], [ 0, 1, 7], [ 0, 7,10], [ 0,10,11],
        [ 1, 5, 9], [ 5,11, 4], [11,10, 2], [10, 7, 6], [ 7, 1, 8],
        [ 3, 9, 4], [ 3, 4, 2], [ 3, 2, 6], [ 3, 6, 8], [ 3, 8, 9],
        [ 4, 9, 5], [ 2, 4,11], [ 6, 2,10], [ 8, 6, 7], [ 9, 8, 1],
    ], dtype=np.int64)
    return v, f


# ─────────────────────────── subdivision ───────────────────────────────
def icosphere(subdivisions: int = 2):
    """Loop-subdivided icosphere projected onto the unit sphere.

    subdivisions=0 → 12 v, 20 f
    subdivisions=1 → 42 v, 80 f
    subdivisions=2 → 162 v, 320 f
    """
    verts, faces = _icosahedron()
    verts = verts.tolist()

    for _ in range(subdivisions):
        cache: dict[tuple[int, int], int] = {}

        def midpoint(a: int, b: int) -> int:
            key = (a, b) if a < b else (b, a)
            hit = cache.get(key)
            if hit is not None:
                return hit
            va = np.asarray(verts[a])
            vb = np.asarray(verts[b])
            m = va + vb
            m /= np.linalg.norm(m)
            idx = len(verts)
            verts.append(m.tolist())
            cache[key] = idx
            return idx

        new_faces = []
        for (a, b, c) in faces:
            ab = midpoint(a, b)
            bc = midpoint(b, c)
            ca = midpoint(c, a)
            new_faces.append([a,  ab, ca])
            new_faces.append([b,  bc, ab])
            new_faces.append([c,  ca, bc])
            new_faces.append([ab, bc, ca])
        faces = np.asarray(new_faces, dtype=np.int64)

    return np.asarray(verts, dtype=np.float64), faces


# ─────────────────────────── mass matrix ──────────────────────────────
def vertex_areas(verts: np.ndarray, faces: np.ndarray) -> np.ndarray:
    """Barycentric vertex area: each vertex gets 1/3 of each incident face area."""
    N = verts.shape[0]
    a = np.zeros(N)
    va = verts[faces[:, 0]]
    vb = verts[faces[:, 1]]
    vc = verts[faces[:, 2]]
    # face area = 0.5 * |(b-a) × (c-a)|
    face_area = 0.5 * np.linalg.norm(np.cross(vb - va, vc - va), axis=1)
    for k in range(3):
        np.add.at(a, faces[:, k], face_area / 3.0)
    return a


# ─────────────────────────── cotangent weights ────────────────────────
def cotangent_weights(verts: np.ndarray, faces: np.ndarray):
    """Return (L, M_diag) where L is the (signed) cotangent Laplacian:
        L_ii = -Σ_j w_ij
        L_ij =  w_ij   (off-diagonal, i ≠ j)
        w_ij = ½ (cot α + cot β)   for edge (i,j) in adjacent triangles
    Note: L is symmetric and negative semi-definite.
    (Lu)_i ≈ A_i · Δu(v_i)  for smooth u, where Δ is Laplace-Beltrami.
    """
    N = verts.shape[0]
    I, J, W = [], [], []
    for (i, j, k) in faces:
        vi, vj, vk = verts[i], verts[j], verts[k]

        # vectors around each vertex of this triangle
        def cot_at(apex, a, b):
            u = a - apex
            v = b - apex
            dot = np.dot(u, v)
            crs = np.linalg.norm(np.cross(u, v))
            return dot / max(crs, 1e-12)

        cot_i = cot_at(vi, vj, vk)   # weights edge (j,k)
        cot_j = cot_at(vj, vk, vi)   # weights edge (k,i)
        cot_k = cot_at(vk, vi, vj)   # weights edge (i,j)

        for (a, b, c) in [(j, k, cot_i), (k, i, cot_j), (i, j, cot_k)]:
            w = 0.5 * c
            # off-diagonal +w (both directions)
            I.append(a); J.append(b); W.append(+w)
            I.append(b); J.append(a); W.append(+w)
            # diagonal -w (both sides)
            I.append(a); J.append(a); W.append(-w)
            I.append(b); J.append(b); W.append(-w)

    L = coo_matrix((W, (I, J)), shape=(N, N)).tocsr()
    M = vertex_areas(verts, faces)
    return L, M


# ─────────────────────────── Laplace-Beltrami ─────────────────────────
def laplace_beltrami(verts: np.ndarray, faces: np.ndarray):
    """Return the discrete Laplace-Beltrami operator Δ = M^(-1) L as sparse csr.

    For u ≈ smooth function on the surface, (Δu)_i ≈ Δ_s u(v_i)
    (in the mathematician's sign convention: Δu = ∂²u/∂s² on 1D, positive at minima).

    Eigenvalues of -Δ on the unit sphere approximate ℓ(ℓ+1):
        ℓ=0: λ=0  (×1)
        ℓ=1: λ=2  (×3)
        ℓ=2: λ=6  (×5)
        ℓ=3: λ=12 (×7)
        ...
    """
    L, M = cotangent_weights(verts, faces)
    Minv = diags(1.0 / M)
    return (Minv @ L).tocsr()


# ─────────────────────────── vertex adjacency ─────────────────────────
def face_adjacency(n_verts: int, faces: np.ndarray):
    """Per-vertex neighbor list derived from face connectivity."""
    adj = [set() for _ in range(n_verts)]
    for (a, b, c) in faces:
        adj[a].add(b); adj[a].add(c)
        adj[b].add(a); adj[b].add(c)
        adj[c].add(a); adj[c].add(b)
    return [sorted(list(s)) for s in adj]


# ─────────────────────────── spectrum verification ────────────────────
def _theoretical_spectrum(k: int):
    """First k eigenvalues of -Δ on unit sphere: ℓ(ℓ+1) with multiplicity (2ℓ+1)."""
    out, ell = [], 0
    while len(out) < k:
        out.extend([ell * (ell + 1)] * (2 * ell + 1))
        ell += 1
    return np.asarray(out[:k], dtype=float)


def verify_spectrum(verts: np.ndarray, faces: np.ndarray, k: int = 30, tol: float = 0.05,
                    check_through_ell: int = 4):
    """Print the first `k` eigenvalues of the discrete Laplace-Beltrami,
    compare to ℓ(ℓ+1), and return True iff every eigenvalue up through
    ℓ = `check_through_ell` matches within `tol`.

    Uses the generalized eigenproblem L φ = λ M φ, so eigenvalues are real
    without numerical drift from the M^(-1) asymmetry.
    """
    L, M = cotangent_weights(verts, faces)
    # Solve -L φ = λ M φ  (dense; 162 verts is fine)
    eigs = eigh(-L.toarray(), np.diag(M), eigvals_only=True)
    eigs = np.sort(eigs)[:k]
    theory = _theoretical_spectrum(k)

    # count of eigenvalues up through the requested ℓ: Σ (2ℓ+1) = (ℓ+1)²
    n_required = (check_through_ell + 1) ** 2

    print(f"{'idx':>3}  {'ℓ':>3}  {'computed':>12}  {'theory ℓ(ℓ+1)':>14}  {'error %':>10}")
    print("-" * 60)
    ell = 0
    ell_count = 0
    max_err_required = 0.0
    for i in range(k):
        if ell_count >= 2 * ell + 1:
            ell += 1
            ell_count = 0
        ell_count += 1
        t = theory[i]
        e = eigs[i]
        err_pct = abs(e - t) / t * 100.0 if t > 0 else abs(e) * 100.0
        marker = ""
        if i < n_required:
            max_err_required = max(max_err_required, err_pct / 100.0)
            if err_pct / 100.0 > tol:
                marker = " ← over tolerance"
        print(f"{i:>3}  {ell:>3}  {e:>12.5f}  {t:>14.0f}  {err_pct:>9.2f}%{marker}")

    passed = max_err_required < tol
    print("-" * 60)
    print(f"First {n_required} eigenvalues (through ℓ={check_through_ell}) within {tol*100:.0f}%: "
          f"max error = {max_err_required*100:.2f}%  →  {'PASS' if passed else 'FAIL'}")
    return passed


# ─────────────────────────── standalone test ──────────────────────────
def _main():
    print("=" * 64)
    print("mesh_utils.py — Stage 1 self-test")
    print("=" * 64)
    for sub in (0, 1, 2, 3):
        v, f = icosphere(sub)
        print(f"  subdivisions={sub}: {len(v):5d} verts, {len(f):5d} faces")
    print()

    verts, faces = icosphere(3)
    print(f"Using icosphere(subdivisions=3): {len(verts)} vertices, {len(faces)} faces\n")

    # sanity: all on unit sphere
    radii = np.linalg.norm(verts, axis=1)
    print(f"  vertex radii: min={radii.min():.6f}  max={radii.max():.6f}  "
          f"(should all be 1.0)")
    assert abs(radii.min() - 1.0) < 1e-10 and abs(radii.max() - 1.0) < 1e-10

    # sanity: total area ≈ 4π
    M = vertex_areas(verts, faces)
    print(f"  sum(vertex areas) = {M.sum():.6f}   (unit sphere area 4π = {4*np.pi:.6f})\n")

    # spectrum — require clean match through ℓ=4 (25 eigenvalues), show 30 for context
    passed = verify_spectrum(verts, faces, k=30, tol=0.05, check_through_ell=4)
    print()
    print("=" * 64)
    print("Stage 1 result:", "PASS ✓" if passed else "FAIL ✗")
    print("=" * 64)
    return passed


if __name__ == "__main__":
    ok = _main()
    import sys
    sys.exit(0 if ok else 1)
