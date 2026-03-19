"""Async client for the Swift EventKitCLI subprocess."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from server.bridge.models import BridgeRequest, BridgeResponse

logger = logging.getLogger(__name__)


class BridgeError(Exception):
    """Raised when the Swift bridge encounters an error."""


class SwiftBridge:
    """Manages a long-lived Swift CLI subprocess.

    Communication is via newline-delimited JSON over stdin/stdout.
    Each request carries a UUID; responses are correlated by that ID.
    """

    def __init__(self, binary_path: str) -> None:
        self._binary_path = binary_path
        self._process: asyncio.subprocess.Process | None = None
        self._pending: dict[str, asyncio.Future[BridgeResponse]] = {}
        self._lock = asyncio.Lock()
        self._reader_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Spawn the Swift CLI subprocess."""
        if not Path(self._binary_path).exists():
            msg = (
                f"Swift bridge binary not found at {self._binary_path}. "
                "Run ./scripts/build-swift.sh on macOS to compile it."
            )
            raise BridgeError(msg)

        self._process = await asyncio.create_subprocess_exec(
            self._binary_path,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._reader_task = asyncio.create_task(self._read_responses())
        logger.info("Swift bridge started (pid=%s)", self._process.pid)

    async def stop(self) -> None:
        """Terminate the Swift CLI subprocess."""
        if self._reader_task:
            self._reader_task.cancel()
            self._reader_task = None
        if self._process and self._process.returncode is None:
            self._process.terminate()
            await self._process.wait()
            logger.info("Swift bridge stopped")
        self._process = None

    async def send_command(
        self, command: str, params: dict[str, Any]
    ) -> BridgeResponse:
        """Send a command to the Swift CLI and await the correlated response."""
        if self._process is None or self._process.returncode is not None:
            raise BridgeError("Bridge not started")

        request = BridgeRequest(command=command, params=params)
        loop = asyncio.get_event_loop()
        future: asyncio.Future[BridgeResponse] = loop.create_future()

        async with self._lock:
            self._pending[request.id] = future

        line = request.model_dump_json() + "\n"
        assert self._process.stdin is not None
        self._process.stdin.write(line.encode())
        await self._process.stdin.drain()

        logger.debug("Sent command: %s (id=%s)", command, request.id)

        try:
            return await asyncio.wait_for(future, timeout=30.0)
        except TimeoutError:
            self._pending.pop(request.id, None)
            raise BridgeError(f"Command '{command}' timed out after 30s") from None

    async def _read_responses(self) -> None:
        """Background task: read stdout lines and resolve pending futures."""
        assert self._process is not None
        assert self._process.stdout is not None

        while True:
            line = await self._process.stdout.readline()
            if not line:
                logger.warning("Swift bridge stdout closed")
                break

            try:
                response = BridgeResponse.model_validate_json(line)
            except Exception:
                logger.warning(
                    "Unparseable bridge output: %s",
                    line.decode(errors="replace"),
                )
                continue

            future = self._pending.pop(response.id, None)
            if future and not future.done():
                future.set_result(response)
            else:
                logger.warning("No pending request for response id=%s", response.id)
