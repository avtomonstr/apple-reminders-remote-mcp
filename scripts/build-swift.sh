#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "Building EventKitCLI..."
cd "$PROJECT_ROOT/swift-bridge"
swift build -c release

BINARY="$PROJECT_ROOT/swift-bridge/.build/release/EventKitCLI"
if [ -f "$BINARY" ]; then
    echo "Build successful: $BINARY"
else
    echo "Build failed: binary not found at $BINARY" >&2
    exit 1
fi
