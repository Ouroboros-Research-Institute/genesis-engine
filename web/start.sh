#!/usr/bin/env bash
# Genesis Engine — local web visualization
# Serves ~/genesis-engine/web/ and the sibling results/ via a single
# HTTP server rooted at ~/genesis-engine/web/ (results is symlinked in).

set -e
cd "$(dirname "$0")"

PORT="${1:-3000}"

echo ""
echo "  ╭────────────────────────────────────────────────────────╮"
echo "  │  GENESIS ENGINE · Local Visualization                  │"
echo "  │                                                        │"
echo "  │  Serving at:  http://localhost:${PORT}                       │"
echo "  │                                                        │"
echo "  │  Views:                                                │"
echo "  │    • LIVE SIMULATION  — real-time protocell dynamics   │"
echo "  │    • MONTE CARLO      — N=500 results from disk        │"
echo "  │                                                        │"
echo "  │  Press Ctrl-C to stop.                                 │"
echo "  ╰────────────────────────────────────────────────────────╯"
echo ""

exec /opt/homebrew/bin/python3 server.py "$PORT"
