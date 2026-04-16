"""
Fig 6 capture — 3-panel composite showcasing the improved dashboard.

Panels:
  1. LIVE 1D at Phase D   — canvas + full side panel (LATCHED + CURRENT STATE)
  2. LIVE 2D SPHERE       — MAX_CELLS=30 grid with whatever phase that seed reaches
  3. MONTE CARLO (N=500)  — the aggregate statistics view

Each panel is captured at its native resolution, then composited side-by-side
into fig6_dashboard_screenshot.png (and a taller fig6_dashboard_vertical.png
for rotating captions). Individual panels are also saved in
paper/figures/fig6_panels/.

Strategy for the live views:
  - Pause the RAF loop.
  - Drive the sim via window.__genesis.stepN / world2d.step, bypassing
    headless RAF throttling.
  - Retry up to MAX_ATTEMPTS on extinction; for 2D we accept any final
    state (it's a stochastic demo, not the evidence).
  - Manually refresh the DOM stats before screenshotting (the RAF loop
    is paused so updateUI is also paused).
"""
from __future__ import annotations
import time
from pathlib import Path
from playwright.sync_api import sync_playwright
from PIL import Image

URL = "http://localhost:3000/"
# repo-relative: <repo>/paper/figures/
FIG_DIR = Path(__file__).resolve().parents[1] / "figures"
PANEL_DIR = FIG_DIR / "fig6_panels"
FIG_DIR.mkdir(parents=True, exist_ok=True)
PANEL_DIR.mkdir(parents=True, exist_ok=True)

COMPOSITE_H  = FIG_DIR / "fig6_dashboard_screenshot.png"
COMPOSITE_V  = FIG_DIR / "fig6_dashboard_vertical.png"

# 1D settings
MAX_TICKS_1D = 40_000
BATCH        = 500
POST_D_SETTLE = 3000
MAX_ATTEMPTS  = 10

# 2D settings
MAX_TICKS_2D = 12_000
BATCH_2D     = 500


def log(*a, **kw): print(*a, **kw, flush=True)


def capture_1d(page) -> Path:
    log("\n=== PANEL 1 — LIVE 1D ===")
    page.click("button.tab[data-view='sim']")
    time.sleep(0.3)
    page.click("#btn-play")               # pause
    time.sleep(0.1)
    page.click(".btn.sp[data-speed='10']")
    time.sleep(0.1)

    def hard_reset_1d():
        page.evaluate("""() => {
            const g = window.__genesis;
            g.world.reset();
            g.drawWorld(g.ctx, g.world);
        }""")

    def step_1d(n):
        return page.evaluate(f"() => window.__genesis.stepN({n})")

    final = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        log(f"  attempt {attempt}")
        hard_reset_1d()
        reached_D = False
        for k in range(0, MAX_TICKS_1D, BATCH):
            s = step_1d(BATCH)
            if s["phase"] == "D":
                reached_D = True
                log(f"    D at t={s['tick']} (B={s['B']} C={s['C']} D={s['D']})")
                break
            if s["pop"] == 0:
                log(f"    extinction at t={s['tick']}")
                break
        if reached_D:
            s = step_1d(POST_D_SETTLE)
            log(f"    settled pop={s['pop']} S={s['S']:.3f} CV={s['CV']:.3f} gen={s['gen']}")
            final = s
            break
    if final is None:
        raise RuntimeError("1D did not reach D")

    # refresh DOM (replicates updateUI's key fields)
    page.evaluate("""() => {
        const g = window.__genesis;
        g.drawWorld(g.ctx, g.world);
        const s = g.world.stats, ph = g.world.phases, w = g.world;
        document.getElementById('s-pop').textContent = s.pop;
        document.getElementById('s-res').textContent = Math.round(s.resource).toString();
        document.getElementById('s-s').textContent   = s.mean_s.toFixed(3);
        document.getElementById('s-cv').textContent  = s.mean_cv.toFixed(3);
        document.getElementById('s-div').textContent = w.total_div;
        document.getElementById('s-gen').textContent = s.max_gen;
        document.getElementById('o-tick').textContent  = w.tick.toLocaleString();
        document.getElementById('o-phase').textContent = s.phase;
        document.getElementById('ev-B').textContent = ph.B_tick > 0 ? 't = ' + ph.B_tick.toLocaleString() : '—';
        document.getElementById('ev-C').textContent = ph.C_tick > 0 ? 't = ' + ph.C_tick.toLocaleString() : '—';
        document.getElementById('ev-D').textContent = ph.D_tick > 0 ? 't = ' + ph.D_tick.toLocaleString() : '—';
        ['A','B','C','D'].forEach((p, i) => {
            const row = document.querySelectorAll('#view-sim .phase-row')[i];
            const reached = p === 'A' ? true : ph[p];
            row.classList.toggle('reached', !!reached);
            row.classList.toggle('current', s.phase === p);
        });
        // CURRENT STATE — call updateCurrentState via its global if exposed,
        // otherwise fallback: set the raw fields manually.
        const P = { B_CV:0.25, C_S:0.25, D_S:0.35, D_CV:0.30, D_GEN:5 };
        const cv = s.mean_cv, pS = s.mean_s, gen = s.max_gen;
        const badge = document.getElementById('cs-badge');
        const phase = (cv>0 && cv<P.B_CV && pS>P.D_S && cv<P.D_CV && gen>=P.D_GEN) ? 'D'
                    : (cv>0 && cv<P.B_CV && pS>P.C_S) ? 'C'
                    : (cv>0 && cv<P.B_CV) ? 'B' : 'A';
        badge.textContent = phase;
        badge.setAttribute('data-phase', phase);
        document.getElementById('cs-cv-v').textContent  = cv.toFixed(3);
        document.getElementById('cs-s-v').textContent   = pS.toFixed(3);
        document.getElementById('cs-gen-v').textContent = gen;
        const ok = 'ok', bad = 'bad';
        document.getElementById('cs-cv-gate').innerHTML  =
            `[ <span class="${cv>0&&cv<P.B_CV?ok:bad}">B&lt;0.25 ${cv>0&&cv<P.B_CV?'✓':'✗'}</span> · `
          + `<span class="${cv>0&&cv<P.D_CV?ok:bad}">D&lt;0.30 ${cv>0&&cv<P.D_CV?'✓':'✗'}</span> ]`;
        document.getElementById('cs-s-gate').innerHTML  =
            `[ <span class="${pS>P.C_S?ok:bad}">C&gt;0.25 ${pS>P.C_S?'✓':'✗'}</span> · `
          + `<span class="${pS>P.D_S?ok:bad}">D&gt;0.35 ${pS>P.D_S?'✓':'✗'}</span> ]`;
        document.getElementById('cs-gen-gate').innerHTML  =
            `[ <span class="${gen>=P.D_GEN?ok:bad}">D≥5 ${gen>=P.D_GEN?'✓':'✗'}</span> ]`;
    }""")
    time.sleep(0.3)
    out = PANEL_DIR / "panel_1d.png"
    page.screenshot(path=str(out), full_page=False)
    log(f"  saved {out} ({out.stat().st_size:,} bytes)")
    return out


def capture_2d(page) -> Path:
    log("\n=== PANEL 2 — LIVE 2D SPHERE ===")
    page.click("button.tab[data-view='sphere']")
    time.sleep(0.8)
    page.click("#btn2-play")               # pause
    time.sleep(0.1)

    def hard_reset_2d():
        page.evaluate("() => { window.__genesis.world2d.reset(); }")

    def step_2d(n):
        return page.evaluate(f"""() => {{
            const w = window.__genesis.world2d;
            for (let i = 0; i < {n}; i++) w.step();
            return {{ tick: w.tick, pop: w.stats.pop,
                     S: w.stats.mean_s, CV: w.stats.mean_cv,
                     phase: w.stats.phase, gen: w.stats.max_gen,
                     B: w.phases.B_tick, C: w.phases.C_tick,
                     D: w.phases.D_tick }};
        }}""")

    # 2D is stochastic — accept any final state where pop>5 and there's
    # visible pattern (S>0.3) OR a latched transition.
    final = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        log(f"  attempt {attempt}")
        hard_reset_2d()
        extinct = False
        last = None
        for k in range(0, MAX_TICKS_2D, BATCH_2D):
            s = step_2d(BATCH_2D)
            last = s
            if s["pop"] == 0:
                log(f"    extinction at t={s['tick']}")
                extinct = True
                break
            if s["phase"] == "D":
                log(f"    D at t={s['tick']}")
                break
        if not extinct and last and last["pop"] > 5:
            final = last
            log(f"    final pop={last['pop']} S={last['S']:.3f} "
                f"CV={last['CV']:.3f} gen={last['gen']} ph={last['phase']}")
            break
    if final is None:
        raise RuntimeError("2D failed to produce a viable population")

    # refresh 2D DOM
    page.evaluate("""() => {
        window.__genesis.redraw2d && window.__genesis.redraw2d();
        const w = window.__genesis.world2d;
        const s = w.stats, ph = w.phases;
        document.getElementById('s2-pop').textContent = s.pop;
        document.getElementById('s2-res').textContent = Math.round(s.resource).toString();
        document.getElementById('s2-s').textContent   = s.mean_s.toFixed(3);
        document.getElementById('s2-cv').textContent  = s.mean_cv.toFixed(3);
        document.getElementById('s2-div').textContent = w.total_div;
        document.getElementById('s2-gen').textContent = s.max_gen;
        document.getElementById('o2-tick').textContent  = w.tick.toLocaleString();
        document.getElementById('o2-phase').textContent = s.phase;
        document.getElementById('ev2-B').textContent = ph.B_tick > 0 ? 't = ' + ph.B_tick.toLocaleString() : '—';
        document.getElementById('ev2-C').textContent = ph.C_tick > 0 ? 't = ' + ph.C_tick.toLocaleString() : '—';
        document.getElementById('ev2-D').textContent = ph.D_tick > 0 ? 't = ' + ph.D_tick.toLocaleString() : '—';
        ['A','B','C','D'].forEach((p, i) => {
            const row = document.querySelectorAll('#view-sphere .phase-row')[i];
            const reached = p === 'A' ? true : ph[p];
            row.classList.toggle('reached', !!reached);
            row.classList.toggle('current', s.phase === p);
        });
        const P = { B_CV:0.25, C_S:0.25, D_S:0.35, D_CV:0.30, D_GEN:5 };
        const cv = s.mean_cv, pS = s.mean_s, gen = s.max_gen;
        const badge = document.getElementById('cs2-badge');
        const phase = (cv>0 && cv<P.B_CV && pS>P.D_S && cv<P.D_CV && gen>=P.D_GEN) ? 'D'
                    : (cv>0 && cv<P.B_CV && pS>P.C_S) ? 'C'
                    : (cv>0 && cv<P.B_CV) ? 'B' : 'A';
        badge.textContent = phase;
        badge.setAttribute('data-phase', phase);
        document.getElementById('cs2-cv-v').textContent  = cv.toFixed(3);
        document.getElementById('cs2-s-v').textContent   = pS.toFixed(3);
        document.getElementById('cs2-gen-v').textContent = gen;
        const ok = 'ok', bad = 'bad';
        document.getElementById('cs2-cv-gate').innerHTML  =
            `[ <span class="${cv>0&&cv<P.B_CV?ok:bad}">B&lt;0.25 ${cv>0&&cv<P.B_CV?'✓':'✗'}</span> · `
          + `<span class="${cv>0&&cv<P.D_CV?ok:bad}">D&lt;0.30 ${cv>0&&cv<P.D_CV?'✓':'✗'}</span> ]`;
        document.getElementById('cs2-s-gate').innerHTML  =
            `[ <span class="${pS>P.C_S?ok:bad}">C&gt;0.25 ${pS>P.C_S?'✓':'✗'}</span> · `
          + `<span class="${pS>P.D_S?ok:bad}">D&gt;0.35 ${pS>P.D_S?'✓':'✗'}</span> ]`;
        document.getElementById('cs2-gen-gate').innerHTML  =
            `[ <span class="${gen>=P.D_GEN?ok:bad}">D≥5 ${gen>=P.D_GEN?'✓':'✗'}</span> ]`;
    }""")
    time.sleep(0.3)
    out = PANEL_DIR / "panel_2d.png"
    page.screenshot(path=str(out), full_page=False)
    log(f"  saved {out} ({out.stat().st_size:,} bytes)")
    return out


def capture_mc(page) -> Path:
    log("\n=== PANEL 3 — MONTE CARLO ===")
    page.click("button.tab[data-view='results']")
    time.sleep(1.0)      # results view hydrates from JSON
    out = PANEL_DIR / "panel_mc.png"
    page.screenshot(path=str(out), full_page=False)
    log(f"  saved {out} ({out.stat().st_size:,} bytes)")
    return out


def composite(paths: list[Path]) -> None:
    imgs = [Image.open(p).convert("RGB") for p in paths]
    # normalize height (shortest wins, proportional scaling)
    target_h = min(img.height for img in imgs)
    scaled = []
    for img in imgs:
        new_w = int(img.width * target_h / img.height)
        scaled.append(img.resize((new_w, target_h), Image.LANCZOS))
    GAP = 12
    BG = (6, 10, 18)   # matches --bg
    total_w = sum(img.width for img in scaled) + GAP * (len(scaled) - 1)
    comp = Image.new("RGB", (total_w, target_h), BG)
    x = 0
    for img in scaled:
        comp.paste(img, (x, 0))
        x += img.width + GAP
    comp.save(COMPOSITE_H, "PNG", optimize=True)
    log(f"\n✓ wrote {COMPOSITE_H} ({COMPOSITE_H.stat().st_size:,} bytes, "
        f"{comp.width}x{comp.height})")

    # vertical variant (uniform width)
    target_w = min(img.width for img in imgs)
    scaled_v = []
    for img in imgs:
        new_h = int(img.height * target_w / img.width)
        scaled_v.append(img.resize((target_w, new_h), Image.LANCZOS))
    total_h = sum(img.height for img in scaled_v) + GAP * (len(scaled_v) - 1)
    compv = Image.new("RGB", (target_w, total_h), BG)
    y = 0
    for img in scaled_v:
        compv.paste(img, (0, y))
        y += img.height + GAP
    compv.save(COMPOSITE_V, "PNG", optimize=True)
    log(f"✓ wrote {COMPOSITE_V} ({COMPOSITE_V.stat().st_size:,} bytes, "
        f"{compv.width}x{compv.height})")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # tall viewport so CURRENT STATE fits without scroll
        ctx = browser.new_context(viewport={"width": 1680, "height": 1400},
                                  device_scale_factor=2)
        page = ctx.new_page()
        err = []
        page.on("pageerror", lambda e: err.append(f"[PAGEERROR] {e}"))
        page.goto(URL, wait_until="networkidle", timeout=20000)
        time.sleep(0.5)

        p1 = capture_1d(page)
        p2 = capture_2d(page)
        p3 = capture_mc(page)
        browser.close()

        composite([p1, p2, p3])
        if err:
            log("\nerrors seen:", err[-5:])

if __name__ == "__main__":
    main()
