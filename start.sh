#!/usr/bin/env bash
# start.sh — launch things-mcp over HTTP on the Mac's Tailscale IP
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

TAILSCALE_IP="$(~/.local/bin/tailscale ip -4 2>/dev/null || tailscale ip -4 2>/dev/null || echo '0.0.0.0')"

export THINGS_MCP_TRANSPORT=http
export THINGS_MCP_HOST="${THINGS_MCP_HOST:-$TAILSCALE_IP}"
export THINGS_MCP_PORT="${THINGS_MCP_PORT:-3400}"

echo "Things3 MCP → http://${THINGS_MCP_HOST}:${THINGS_MCP_PORT}"

cd "$SCRIPT_DIR"
~/.local/bin/uv run python api_server.py
