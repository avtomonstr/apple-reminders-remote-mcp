"""ASGI app assembly: mounts FastMCP, adds auth middleware, manages bridge lifespan."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from starlette.applications import Starlette
from starlette.routing import Route

import server.tools.reminders_lists
import server.tools.reminders_subtasks
import server.tools.reminders_tasks  # noqa: F401
from server.auth import BearerAuthMiddleware
from server.bridge.swift_bridge import SwiftBridge
from server.mcp_instance import mcp, set_bridge

load_dotenv()

logger = logging.getLogger(__name__)


def create_asgi_app() -> Starlette:
    """Build the ASGI app: FastMCP mounted at /mcp, wrapped with auth."""
    token = os.environ.get("REMINDERS_API_TOKEN", "")
    if not token:
        logger.warning(
            "REMINDERS_API_TOKEN not set — all /mcp requests will be rejected"
        )

    bridge_path = os.environ.get(
        "SWIFT_BRIDGE_PATH", "./swift-bridge/.build/release/EventKitCLI"
    )

    # Trigger lazy session manager creation, then grab the ASGI endpoint
    mcp.streamable_http_app()
    session_manager = mcp.session_manager
    from mcp.server.fastmcp.server import StreamableHTTPASGIApp

    mcp_endpoint = StreamableHTTPASGIApp(session_manager)

    @asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        bridge = SwiftBridge(binary_path=bridge_path)
        try:
            await bridge.start()
            set_bridge(bridge)
            logger.info("Swift bridge started")
        except Exception:
            logger.warning(
                "Swift bridge not available (expected on non-macOS). "
                "Tools will return errors."
            )
            set_bridge(None)
            bridge = None  # type: ignore[assignment]
        try:
            async with session_manager.run():
                yield
        finally:
            if bridge:
                await bridge.stop()
            set_bridge(None)

    app = Starlette(
        routes=[
            Route("/mcp", endpoint=mcp_endpoint, methods=["GET", "POST", "DELETE"]),
        ],
        lifespan=lifespan,
    )
    app.add_middleware(BearerAuthMiddleware, token=token)
    return app
