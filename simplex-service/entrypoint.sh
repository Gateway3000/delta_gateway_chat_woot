#!/bin/sh
set -eu

DB="${SIMPLEX_DB:-/data/simplex}"
INTERNAL_PORT=5226
LISTEN_PORT="${SIMPLEX_PORT:-5225}"

# The CLI binds its WebSocket port to 127.0.0.1 only. Run it on an internal
# loopback port, then expose it on all interfaces with socat so the gateway
# (a separate container) can connect at ws://simplex-chat:5225.
simplex-chat -p "$INTERNAL_PORT" -d "$DB" &
cli_pid=$!

# Give the CLI a moment to create its WS listener before proxying to it.
sleep 2

trap 'kill "$cli_pid" 2>/dev/null || true' INT TERM

exec socat "TCP-LISTEN:${LISTEN_PORT},fork,reuseaddr" "TCP:127.0.0.1:${INTERNAL_PORT}"
