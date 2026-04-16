#!/usr/bin/env bash
# build_static.sh — prepare a self-contained static web/ directory
# suitable for Cloudflare Pages / GitHub Pages / any static host.
#
# What this does
#   * Replaces the web/results symlink (which points outside web/ and breaks
#     on static hosts) with real copies of the CSVs that results.js fetches.
#   * Copies paper/paper_data.json and paper/figures/ into web/ for the
#     Results tab to consume without leaving the publish root.
#
# Idempotent — safe to run multiple times. Run from repo root:
#     bash web/build_static.sh
#
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root"

# 1. Replace symlink with real directory
if [ -L "web/results" ]; then
  rm "web/results"
fi
mkdir -p web/results/ablations
cp -f results/summary.csv                       web/results/summary.csv
cp -f results/ablations/ablation_summary.csv    web/results/ablations/ablation_summary.csv

# 2. Mirror paper data for the Monte Carlo tab
mkdir -p web/paper/figures
cp -f paper/paper_data.json                     web/paper/paper_data.json
cp -f paper/figures/*.png                       web/paper/figures/ 2>/dev/null || true

echo "✓ web/ is now self-contained and static-host ready:"
ls -la web/results web/paper 2>/dev/null | sed 's/^/   /'
