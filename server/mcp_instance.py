"""FastMCP instance and bridge singleton.

This module is the single source of truth for the `mcp` FastMCP object
and the `get_bridge()` accessor. Both `server.app` and `server.tools.*`
import from here — never from each other — to avoid circular imports.
"""

from __future__ import annotations

import logging

from mcp.server.fastmcp import FastMCP

from server.bridge.swift_bridge import SwiftBridge

logger = logging.getLogger(__name__)

mcp = FastMCP(
    "apple-reminders-remote",
    stateless_http=True,
    json_response=True,
)

# Bridge singleton — set by app.py lifespan, read by tools
_bridge: SwiftBridge | None = None


def set_bridge(bridge: SwiftBridge | None) -> None:
    """Called by app.py lifespan to set/clear the bridge."""
    global _bridge
    _bridge = bridge


def get_bridge() -> SwiftBridge:
    """Get the active SwiftBridge instance. Raises if not started."""
    if _bridge is None:
        msg = "SwiftBridge not initialized. Server still starting?"
        raise RuntimeError(msg)
    return _bridge
