#!/usr/bin/env bash
# start.sh — launch things-mcp over HTTP on loopback, fronted by `tailscale serve`
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Bind loopback only. Tailnet reachability comes from `tailscale serve`, which
# proxies https://<node>.<tailnet>.ts.net:3400 to 127.0.0.1:3400. Binding a
# routable address here would also expose the API — which has no auth — to the
# local LAN, and would contend with serve for the port on the tailnet address.
export THINGS_MCP_TRANSPORT=http
export THINGS_MCP_HOST="${THINGS_MCP_HOST:-127.0.0.1}"
export THINGS_MCP_PORT="${THINGS_MCP_PORT:-3400}"

echo "Things3 MCP → http://${THINGS_MCP_HOST}:${THINGS_MCP_PORT}"

cd "$SCRIPT_DIR"
~/.local/bin/uv run python api_server.py
