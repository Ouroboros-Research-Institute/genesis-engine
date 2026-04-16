# Deploying the Genesis Dashboard to Cloudflare Pages

Target URL: **https://genesis-engine.lucyvpa.com**

The dashboard is a pure static site (HTML + JS + CSS + precomputed data).
Cloudflare Pages will serve it directly from the `web/` directory of this
repo. The `build_static.sh` script flattens symlinks and mirrors
`paper/paper_data.json` + figures into `web/` so nothing outside the publish
root is referenced. The `/api/status` endpoint is used only when the local
Python server is running — on Pages it returns 404 and the dashboard
detects this, stops polling, and shows a "static mode" notice in the
Background Jobs area.

## One-time setup (5 minutes)

### 1. Create the Pages project

1. Log in at <https://dash.cloudflare.com/> with the account that owns
   **lucyvpa.com**.
2. In the left sidebar, click **Workers & Pages → Create → Pages →
   Connect to Git**.
3. Authorize the Cloudflare GitHub App for the `AVADSA25` account if you
   haven't already. Grant it access to `AVADSA25/genesis-engine`.
4. Select repository **`AVADSA25/genesis-engine`**, branch **`main`**, then
   click **Begin setup**.

### 2. Build configuration

Enter exactly these values:

| Field                   | Value                  |
|-------------------------|------------------------|
| Project name            | `genesis-engine`       |
| Production branch       | `main`                 |
| Framework preset        | **None**               |
| Build command           | `bash web/build_static.sh` |
| Build output directory  | `web`                  |
| Root directory          | *(leave blank)*        |
| Environment variables   | *(none required)*      |

Click **Save and Deploy**. The first build takes about 30 seconds. When it
completes, Cloudflare will give you a preview URL like
`https://genesis-engine.pages.dev` — confirm it loads, then proceed.

### 3. Custom domain

1. In the project, go to **Custom domains → Set up a custom domain**.
2. Enter **`genesis-engine.lucyvpa.com`** and click **Continue**.
3. Cloudflare will offer to create the DNS record automatically (a CNAME
   pointing to the Pages project). Click **Activate domain**.
4. Wait ~1 minute for the SSL certificate to provision. The lock icon in
   the browser address bar will confirm success.

### 4. Smoke test (the final gate)

Open <https://genesis-engine.lucyvpa.com> in a fresh browser tab.

- [ ] **Page loads.** The hero banner "Genesis Engine" renders, tabs visible.
- [ ] **1D Live Simulation tab.** Click *Play*. The canvas animates; after a
      few seconds the B/C/D rows on the side panel start latching.
- [ ] **2D Sphere tab.** Click *Play*. A rotating icosphere appears with
      patches that develop magenta spots as patterns form.
- [ ] **Results tab.** The Monte Carlo headline "100 %" banner renders with
      1D / 2D / combined statistics. Ablation grid shows all-green.
- [ ] **Background Jobs area.** Shows "Static deployment — live job status
      disabled" (expected — this is the graceful degradation).
- [ ] **About / Methods tab.** Documentation renders.

If any of the above fail, check **Cloudflare Pages → Deployments → View
build log** for the most recent build.

## Re-deploying after changes

Every `git push` to `main` triggers an automatic rebuild. No manual action
is required.

## Local preview before deploying

```bash
git clone https://github.com/AVADSA25/genesis-engine.git
cd genesis-engine
bash web/build_static.sh          # flatten symlinks, copy paper assets
cd web
python3 -m http.server 3000       # serves http://localhost:3000
```

This mirrors what Cloudflare Pages will serve. The `/api/status` endpoint
is absent (no backend) so the dashboard will display the static-mode
notice — confirming the fallback works before going live.

---

Once the domain resolves, this file can be removed or left in place as a
reproduction record. All URLs already embedded in the paper and in
`CITATION.cff` point at the final production address, so nothing else
needs to be changed post-deploy.
