# Python MCP Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Python MCP server that exposes Apple Reminders as MCP tools over Streamable HTTP, with bearer token auth, communicating with a Swift CLI bridge via JSON-over-stdin/stdout.

**Architecture:** FastMCP server with 3 action-based tools (`reminders_tasks`, `reminders_lists`, `reminders_subtasks`). A `SwiftBridge` class spawns the EventKitCLI binary as a long-lived subprocess, sends newline-delimited JSON commands, and correlates responses by UUID. Bearer token auth is handled via Starlette ASGI middleware wrapping the FastMCP app. The server binds to `127.0.0.1:8000` only — Cloudflare Tunnel provides external HTTPS access.

**Tech Stack:** Python 3.12+, `mcp` SDK (FastMCP), Pydantic v2, uvicorn, `uv` package manager, pytest + pytest-asyncio, ruff, mypy

**Spec:** `CLAUDE.md` in repo root contains the full architecture and requirements.

**Out of scope (separate plan):** Swift EventKit bridge (`swift-bridge/`), Cloudflare Tunnel setup scripts, macOS launch agent plists, `docs/setup.md`. Those require macOS.

---

## File Structure

```
pyproject.toml              — Project config, all deps, ruff/mypy settings
.python-version             — "3.12"
.env.example                — Template env vars

server/
  __init__.py               — Package marker (empty)
  __main__.py               — Entry point: python -m server
  mcp_instance.py           — FastMCP instance + get_bridge() (shared by app.py and tools)
  app.py                    — ASGI app assembly: mounts FastMCP, adds auth middleware, bridge lifespan
  auth.py                   — BearerAuthMiddleware (Starlette ASGI middleware)
  bridge/
    __init__.py             — Package marker, re-exports SwiftBridge
    models.py               — Pydantic models: BridgeRequest, BridgeResponse, ReminderList, Reminder, Subtask
    swift_bridge.py         — SwiftBridge class: subprocess lifecycle, send/receive JSON, request correlation
  tools/
    __init__.py             — Package marker (empty)
    reminders_lists.py      — @mcp.tool() for list CRUD (action: read/create/update/delete)
    reminders_tasks.py      — @mcp.tool() for reminder CRUD with filters
    reminders_subtasks.py   — @mcp.tool() for subtask management

tests/
  __init__.py               — Package marker (empty)
  conftest.py               — Shared fixtures: mock_bridge, mcp test client
  test_auth.py              — Auth middleware unit tests
  test_bridge.py            — SwiftBridge unit tests (mocked subprocess)
  test_tools.py             — Tool handler tests with mocked bridge
```

---

## Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `.python-version`
- Create: `.env.example`
- Create: `server/__init__.py`
- Create: `server/bridge/__init__.py`
- Create: `server/tools/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "apple-reminders-remote-mcp"
version = "0.1.0"
description = "Cross-platform MCP server for Apple Reminders via Cloudflare Tunnel"
requires-python = ">=3.12"
dependencies = [
    "mcp>=1.26.0",
    "pydantic>=2.0",
    "starlette>=0.38.0",
    "uvicorn>=0.30.0",
    "httpx>=0.27.0",
    "python-dotenv>=1.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24.0",
    "ruff>=0.8.0",
    "mypy>=1.13.0",
]

[tool.ruff]
line-length = 88
target-version = "py312"

[tool.ruff.format]
quote-style = "double"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM", "RUF"]

[tool.mypy]
python_version = "3.12"
strict = true
warn_return_any = true
warn_unused_configs = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Create `.python-version`**

```
3.12
```

- [ ] **Step 3: Create `.env.example`**

```bash
# Required: Bearer token for MCP endpoint authentication
REMINDERS_API_TOKEN=your-secret-token-here

# Server config (defaults shown)
HOST=127.0.0.1
PORT=8000

# Path to compiled Swift CLI binary (macOS only)
SWIFT_BRIDGE_PATH=./swift-bridge/.build/release/EventKitCLI
```

- [ ] **Step 4: Create empty `__init__.py` package markers**

Create these four empty files:
- `server/__init__.py`
- `server/bridge/__init__.py`
- `server/tools/__init__.py`
- `tests/__init__.py`

- [ ] **Step 5: Update `.gitignore` with project-specific entries**

Append to existing `.gitignore`:
```gitignore
# Environment
.env

# Swift build artifacts
swift-bridge/.build/

# Cloudflare Tunnel credentials
tunnel/*.json
tunnel/*.yml
!tunnel/config.yml.example

# macOS launch agents with real tokens
*.plist
!tunnel/*.plist.example
```

- [ ] **Step 6: Install dependencies**

Run: `uv sync --all-extras`
Expected: Creates `uv.lock`, installs all deps into `.venv`

- [ ] **Step 7: Verify setup**

Run: `uv run python -c "import mcp; print(mcp.__version__)"`
Expected: Prints mcp version (1.26.0 or higher)

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml .python-version .env.example .gitignore server/__init__.py server/bridge/__init__.py server/tools/__init__.py tests/__init__.py uv.lock
git commit -m "chore: scaffold project with pyproject.toml and package structure"
```

---

## Task 2: Pydantic Bridge Models

**Files:**
- Create: `server/bridge/models.py`
- Create: `tests/test_bridge.py` (first tests)

- [ ] **Step 1: Write failing tests for bridge models**

Create `tests/test_bridge.py`:

```python
"""Tests for Swift bridge models and communication."""

import json

from server.bridge.models import (
    BridgeRequest,
    BridgeResponse,
    Reminder,
    ReminderList,
    Subtask,
)


class TestBridgeRequest:
    def test_serializes_to_json_line(self) -> None:
        req = BridgeRequest(command="list_lists", params={})
        data = json.loads(req.model_dump_json())
        assert data["command"] == "list_lists"
        assert data["params"] == {}
        assert "id" in data  # UUID auto-generated

    def test_id_is_unique(self) -> None:
        req1 = BridgeRequest(command="list_lists", params={})
        req2 = BridgeRequest(command="list_lists", params={})
        assert req1.id != req2.id

    def test_params_included(self) -> None:
        req = BridgeRequest(
            command="create_reminder",
            params={"title": "Buy milk", "list_id": "abc-123"},
        )
        data = json.loads(req.model_dump_json())
        assert data["params"]["title"] == "Buy milk"


class TestBridgeResponse:
    def test_success_response(self) -> None:
        raw = '{"id": "req-1", "success": true, "data": {"name": "Shopping"}}'
        resp = BridgeResponse.model_validate_json(raw)
        assert resp.success is True
        assert resp.data == {"name": "Shopping"}
        assert resp.error is None

    def test_error_response(self) -> None:
        raw = '{"id": "req-1", "success": false, "error": "List not found"}'
        resp = BridgeResponse.model_validate_json(raw)
        assert resp.success is False
        assert resp.error == "List not found"
        assert resp.data is None


class TestReminderList:
    def test_from_dict(self) -> None:
        data = {"id": "list-1", "title": "Shopping", "count": 5, "color": "#FF0000"}
        rlist = ReminderList.model_validate(data)
        assert rlist.id == "list-1"
        assert rlist.title == "Shopping"
        assert rlist.count == 5


class TestReminder:
    def test_minimal_reminder(self) -> None:
        data = {
            "id": "rem-1",
            "title": "Buy milk",
            "list_id": "list-1",
            "list_title": "Shopping",
            "is_completed": False,
            "priority": 0,
        }
        rem = Reminder.model_validate(data)
        assert rem.id == "rem-1"
        assert rem.title == "Buy milk"
        assert rem.is_completed is False
        assert rem.due_date is None
        assert rem.notes is None
        assert rem.tags == []

    def test_full_reminder(self) -> None:
        data = {
            "id": "rem-2",
            "title": "Call dentist",
            "list_id": "list-2",
            "list_title": "Health",
            "is_completed": False,
            "priority": 1,
            "due_date": "2026-03-20T09:00:00Z",
            "notes": "Ask about cleaning [#health] [#urgent]",
            "url": "https://example.com",
        }
        rem = Reminder.model_validate(data)
        assert rem.priority == 1
        assert rem.due_date == "2026-03-20T09:00:00Z"
        assert rem.url == "https://example.com"

    def test_tags_extracted_from_notes(self) -> None:
        data = {
            "id": "rem-3",
            "title": "Test",
            "list_id": "list-1",
            "list_title": "Default",
            "is_completed": False,
            "priority": 0,
            "notes": "Some note [#work] [#urgent]",
        }
        rem = Reminder.model_validate(data)
        assert rem.tags == ["work", "urgent"]


class TestSubtask:
    def test_subtask(self) -> None:
        data = {"id": "sub-1", "title": "Pick up prescription", "is_completed": False}
        sub = Subtask.model_validate(data)
        assert sub.id == "sub-1"
        assert sub.title == "Pick up prescription"
        assert sub.is_completed is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_bridge.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'server.bridge.models'`

- [ ] **Step 3: Implement bridge models**

Create `server/bridge/models.py`:

```python
"""Pydantic models for Swift bridge JSON protocol."""

from __future__ import annotations

import re
import uuid
from typing import Any

from pydantic import BaseModel, Field, computed_field


class BridgeRequest(BaseModel):
    """JSON request sent to the Swift CLI over stdin."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    command: str
    params: dict[str, Any] = Field(default_factory=dict)


class BridgeResponse(BaseModel):
    """JSON response received from the Swift CLI over stdout."""

    id: str
    success: bool
    data: Any | None = None
    error: str | None = None


class ReminderList(BaseModel):
    """A reminder list from EventKit."""

    id: str
    title: str
    count: int = 0
    color: str | None = None


class Subtask(BaseModel):
    """A subtask within a reminder."""

    id: str
    title: str
    is_completed: bool = False


_TAG_PATTERN = re.compile(r"\[#(\w+)]")


class Reminder(BaseModel):
    """A reminder item from EventKit."""

    id: str
    title: str
    list_id: str
    list_title: str
    is_completed: bool = False
    priority: int = 0
    due_date: str | None = None
    notes: str | None = None
    url: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def tags(self) -> list[str]:
        """Extract tags from notes field using [#tag] format."""
        if not self.notes:
            return []
        return _TAG_PATTERN.findall(self.notes)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_bridge.py -v`
Expected: All 9 tests PASS

- [ ] **Step 5: Lint and type-check**

Run: `uv run ruff check server/bridge/models.py && uv run ruff format --check server/bridge/models.py`
Expected: No issues

- [ ] **Step 6: Commit**

```bash
git add server/bridge/models.py tests/test_bridge.py
git commit -m "feat: add Pydantic models for Swift bridge JSON protocol"
```

---

## Task 3: Swift Bridge Client

**Files:**
- Create: `server/bridge/swift_bridge.py`
- Modify: `server/bridge/__init__.py`
- Modify: `tests/test_bridge.py` (add SwiftBridge tests)

- [ ] **Step 1: Write failing tests for SwiftBridge**

Append to `tests/test_bridge.py`:

```python
import asyncio
import json as json_module
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from server.bridge.swift_bridge import SwiftBridge, BridgeError


class TestSwiftBridge:
    async def test_bridge_error_on_missing_binary(self) -> None:
        bridge = SwiftBridge(binary_path="/nonexistent/path/EventKitCLI")
        with pytest.raises(BridgeError, match="Swift bridge binary not found"):
            await bridge.start()

    async def test_send_requires_started_bridge(self) -> None:
        bridge = SwiftBridge(binary_path="/nonexistent/path/EventKitCLI")
        with pytest.raises(BridgeError, match="Bridge not started"):
            await bridge.send_command("list_lists", {})

    async def test_send_command_writes_to_stdin_and_reads_response(self) -> None:
        """Test the real send_command + _read_responses flow with a mock subprocess."""
        bridge = SwiftBridge(binary_path="/fake")

        # Set up mock process
        mock_process = MagicMock()
        mock_process.returncode = None

        # Mock stdin
        written_lines: list[bytes] = []
        mock_process.stdin = MagicMock()
        mock_process.stdin.write = lambda data: written_lines.append(data)
        mock_process.stdin.drain = AsyncMock()

        # Mock stdout — we'll feed it a response after send_command writes
        response_queue: asyncio.Queue[bytes] = asyncio.Queue()

        async def mock_readline() -> bytes:
            return await response_queue.get()

        mock_process.stdout = MagicMock()
        mock_process.stdout.readline = mock_readline

        bridge._process = mock_process
        bridge._pending = {}
        bridge._lock = asyncio.Lock()
        bridge._reader_task = asyncio.create_task(bridge._read_responses())

        # Send command (it will block waiting for response)
        async def send_and_respond() -> BridgeResponse:
            task = asyncio.create_task(bridge.send_command("list_lists", {}))
            # Give send_command time to write to stdin
            await asyncio.sleep(0.01)
            # Parse what was written to extract the request ID
            assert len(written_lines) == 1
            sent = json_module.loads(written_lines[0])
            # Feed matching response to stdout
            resp = {"id": sent["id"], "success": True, "data": [{"id": "l1", "title": "Shopping"}]}
            await response_queue.put(json_module.dumps(resp).encode() + b"\n")
            return await task

        result = await send_and_respond()
        assert result.success is True
        assert result.data == [{"id": "l1", "title": "Shopping"}]

        # Clean up
        bridge._reader_task.cancel()

    async def test_send_command_correlates_by_id(self) -> None:
        """Two concurrent commands get the correct responses matched by ID."""
        bridge = SwiftBridge(binary_path="/fake")

        mock_process = MagicMock()
        mock_process.returncode = None

        written_lines: list[bytes] = []
        mock_process.stdin = MagicMock()
        mock_process.stdin.write = lambda data: written_lines.append(data)
        mock_process.stdin.drain = AsyncMock()

        response_queue: asyncio.Queue[bytes] = asyncio.Queue()

        async def mock_readline() -> bytes:
            return await response_queue.get()

        mock_process.stdout = MagicMock()
        mock_process.stdout.readline = mock_readline

        bridge._process = mock_process
        bridge._pending = {}
        bridge._lock = asyncio.Lock()
        bridge._reader_task = asyncio.create_task(bridge._read_responses())

        # Send two commands concurrently
        task1 = asyncio.create_task(bridge.send_command("list_lists", {}))
        task2 = asyncio.create_task(bridge.send_command("list_reminders", {}))
        await asyncio.sleep(0.01)

        # Parse both request IDs
        assert len(written_lines) == 2
        req1 = json_module.loads(written_lines[0])
        req2 = json_module.loads(written_lines[1])

        # Respond in REVERSE order
        resp2 = {"id": req2["id"], "success": True, "data": "reminders"}
        resp1 = {"id": req1["id"], "success": True, "data": "lists"}
        await response_queue.put(json_module.dumps(resp2).encode() + b"\n")
        await response_queue.put(json_module.dumps(resp1).encode() + b"\n")

        result1 = await task1
        result2 = await task2

        assert result1.data == "lists"
        assert result2.data == "reminders"

        bridge._reader_task.cancel()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_bridge.py::TestSwiftBridge -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'server.bridge.swift_bridge'`

- [ ] **Step 3: Implement SwiftBridge**

Create `server/bridge/swift_bridge.py`:

```python
"""Async client for the Swift EventKitCLI subprocess."""

from __future__ import annotations

import asyncio
import json
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

    async def send_command(self, command: str, params: dict[str, Any]) -> BridgeResponse:
        """Send a command to the Swift CLI and await the correlated response."""
        if self._process is None or self._process.returncode is not None:
            raise BridgeError("Bridge not started")

        request = BridgeRequest(command=command, params=params)
        future: asyncio.Future[BridgeResponse] = asyncio.get_event_loop().create_future()

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
                logger.warning("Unparseable bridge output: %s", line.decode(errors="replace"))
                continue

            future = self._pending.pop(response.id, None)
            if future and not future.done():
                future.set_result(response)
            else:
                logger.warning("No pending request for response id=%s", response.id)
```

- [ ] **Step 4: Update `server/bridge/__init__.py`**

```python
"""Swift bridge client package."""

from server.bridge.models import (
    BridgeRequest,
    BridgeResponse,
    Reminder,
    ReminderList,
    Subtask,
)
from server.bridge.swift_bridge import BridgeError, SwiftBridge

__all__ = [
    "BridgeError",
    "BridgeRequest",
    "BridgeResponse",
    "Reminder",
    "ReminderList",
    "Subtask",
    "SwiftBridge",
]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_bridge.py -v`
Expected: All tests PASS (13 total — 9 model tests + 4 bridge tests)

- [ ] **Step 6: Lint**

Run: `uv run ruff check server/bridge/ && uv run ruff format --check server/bridge/`
Expected: No issues

- [ ] **Step 7: Commit**

```bash
git add server/bridge/swift_bridge.py server/bridge/__init__.py tests/test_bridge.py
git commit -m "feat: add async Swift bridge client with subprocess management"
```

---

## Task 4: Bearer Token Auth Middleware

**Files:**
- Create: `server/auth.py`
- Create: `tests/test_auth.py`

- [ ] **Step 1: Write failing tests for auth middleware**

Create `tests/test_auth.py`:

```python
"""Tests for bearer token authentication middleware."""

from unittest.mock import patch

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from server.auth import BearerAuthMiddleware

TEST_TOKEN = "test-secret-token-123"


def _make_app() -> Starlette:
    """Create a test Starlette app with auth middleware."""

    async def mcp_endpoint(request: Request) -> PlainTextResponse:
        return PlainTextResponse("ok")

    async def health_endpoint(request: Request) -> PlainTextResponse:
        return PlainTextResponse("healthy")

    app = Starlette(
        routes=[
            Route("/mcp", mcp_endpoint, methods=["GET", "POST"]),
            Route("/health", health_endpoint),
        ],
    )
    app.add_middleware(BearerAuthMiddleware, token=TEST_TOKEN)
    return app


class TestBearerAuthMiddleware:
    @pytest.fixture
    def client(self) -> TestClient:
        return TestClient(_make_app())

    def test_mcp_with_valid_token(self, client: TestClient) -> None:
        resp = client.get("/mcp", headers={"Authorization": f"Bearer {TEST_TOKEN}"})
        assert resp.status_code == 200
        assert resp.text == "ok"

    def test_mcp_without_token(self, client: TestClient) -> None:
        resp = client.get("/mcp")
        assert resp.status_code == 401
        assert resp.json()["error"] == "Unauthorized"

    def test_mcp_with_wrong_token(self, client: TestClient) -> None:
        resp = client.get("/mcp", headers={"Authorization": "Bearer wrong-token"})
        assert resp.status_code == 401

    def test_mcp_with_malformed_header(self, client: TestClient) -> None:
        resp = client.get("/mcp", headers={"Authorization": "Basic abc123"})
        assert resp.status_code == 401

    def test_non_mcp_path_no_auth_required(self, client: TestClient) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.text == "healthy"

    def test_mcp_post_with_valid_token(self, client: TestClient) -> None:
        resp = client.post("/mcp", headers={"Authorization": f"Bearer {TEST_TOKEN}"})
        assert resp.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_auth.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'server.auth'`

- [ ] **Step 3: Implement auth middleware**

Create `server/auth.py`:

```python
"""Bearer token authentication middleware for MCP endpoints."""

from __future__ import annotations

import hmac

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class BearerAuthMiddleware(BaseHTTPMiddleware):
    """Validates Bearer token on /mcp routes.

    Non-MCP routes (e.g., /health) pass through without auth.
    """

    def __init__(self, app: object, token: str) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._token = token

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.url.path.startswith("/mcp"):
            auth_header = request.headers.get("authorization", "")
            if not auth_header.startswith("Bearer "):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)

            provided_token = auth_header.removeprefix("Bearer ")
            if not hmac.compare_digest(provided_token, self._token):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)

        return await call_next(request)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_auth.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Lint**

Run: `uv run ruff check server/auth.py && uv run ruff format --check server/auth.py`
Expected: No issues

- [ ] **Step 6: Commit**

```bash
git add server/auth.py tests/test_auth.py
git commit -m "feat: add bearer token auth middleware for MCP endpoints"
```

---

## Task 5: FastMCP App Assembly

**Files:**
- Create: `server/mcp_instance.py`
- Create: `server/app.py`
- Create: `server/__main__.py`

**Architecture note:** The `mcp` FastMCP instance and `get_bridge()` live in `server/mcp_instance.py` — a module with no imports from `server/tools/*` or `server/app`. Both `server/app.py` and `server/tools/*.py` import from `mcp_instance.py`, avoiding circular imports.

- [ ] **Step 1: Write `server/mcp_instance.py`**

This module owns the FastMCP instance and the bridge singleton. It imports nothing from the rest of `server/` (except `bridge/`), so it cannot participate in circular imports.

```python
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
```

- [ ] **Step 2: Write `server/app.py`**

This file assembles the ASGI app: imports `mcp` from `mcp_instance`, imports tools to trigger registration, adds auth middleware and bridge lifespan.

```python
"""ASGI app assembly: mounts FastMCP, adds auth middleware, manages bridge lifespan."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from dotenv import load_dotenv
from starlette.applications import Starlette
from starlette.routing import Mount

from server.auth import BearerAuthMiddleware
from server.bridge.swift_bridge import SwiftBridge
from server.mcp_instance import mcp, set_bridge

# Import tools to trigger @mcp.tool() registration
import server.tools.reminders_lists  # noqa: F401, E402
import server.tools.reminders_subtasks  # noqa: F401, E402
import server.tools.reminders_tasks  # noqa: F401, E402

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
            yield
        finally:
            if bridge:
                await bridge.stop()
            set_bridge(None)

    app = Starlette(
        routes=[Mount("/mcp", app=mcp.streamable_http_app())],
        lifespan=lifespan,
    )
    app.add_middleware(BearerAuthMiddleware, token=token)
    return app
```

- [ ] **Step 3: Write `server/__main__.py`**

```python
"""Entry point: python -m server."""

from __future__ import annotations

import os

import uvicorn
from dotenv import load_dotenv

load_dotenv()


def main() -> None:
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))

    uvicorn.run(
        "server.app:create_asgi_app",
        host=host,
        port=port,
        factory=True,
        log_level="info",
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Verify the server imports cleanly**

Run: `uv run python -c "from server.mcp_instance import mcp, get_bridge; print('mcp_instance OK')"`
Expected: Prints `mcp_instance OK`

Run: `uv run python -c "from server.app import create_asgi_app; print('app OK')"`
Expected: Prints `app OK`

- [ ] **Step 5: Lint**

Run: `uv run ruff check server/mcp_instance.py server/app.py server/__main__.py && uv run ruff format --check server/mcp_instance.py server/app.py server/__main__.py`
Expected: No issues

- [ ] **Step 6: Commit**

```bash
git add server/mcp_instance.py server/app.py server/__main__.py
git commit -m "feat: add FastMCP app assembly with ASGI + auth middleware"
```

---

## Task 6: Reminders Lists Tool

**Files:**
- Create: `server/tools/reminders_lists.py`
- Create: `tests/conftest.py`
- Create: `tests/test_tools.py`

- [ ] **Step 1: Create shared test fixtures**

Create `tests/conftest.py`:

```python
"""Shared test fixtures."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from server.bridge.models import BridgeResponse
from server.bridge.swift_bridge import SwiftBridge


@pytest.fixture
def mock_bridge() -> AsyncMock:
    """A mocked SwiftBridge that returns configurable responses."""
    bridge = AsyncMock(spec=SwiftBridge)
    return bridge


def make_success_response(data: Any) -> BridgeResponse:
    """Helper to create a successful BridgeResponse."""
    return BridgeResponse(id="test", success=True, data=data)


def make_error_response(error: str) -> BridgeResponse:
    """Helper to create an error BridgeResponse."""
    return BridgeResponse(id="test", success=False, error=error)
```

- [ ] **Step 2: Write failing tests for lists tool**

Create `tests/test_tools.py`:

```python
"""Tests for MCP tool handlers with mocked Swift bridge."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from server.bridge.models import BridgeResponse
from server.tools.reminders_lists import handle_reminders_lists
from tests.conftest import make_error_response, make_success_response


class TestRemindersLists:
    async def test_read_lists(self, mock_bridge: AsyncMock) -> None:
        mock_bridge.send_command.return_value = make_success_response(
            [
                {"id": "l1", "title": "Shopping", "count": 3, "color": "#FF0000"},
                {"id": "l2", "title": "Work", "count": 10, "color": "#0000FF"},
            ]
        )
        result = await handle_reminders_lists(mock_bridge, action="read")
        mock_bridge.send_command.assert_awaited_once_with("list_lists", {})
        assert "Shopping" in result
        assert "Work" in result

    async def test_create_list(self, mock_bridge: AsyncMock) -> None:
        mock_bridge.send_command.return_value = make_success_response(
            {"id": "l3", "title": "Groceries", "count": 0}
        )
        result = await handle_reminders_lists(
            mock_bridge, action="create", title="Groceries"
        )
        mock_bridge.send_command.assert_awaited_once_with(
            "create_list", {"title": "Groceries"}
        )
        assert "Groceries" in result

    async def test_create_list_missing_title(self, mock_bridge: AsyncMock) -> None:
        result = await handle_reminders_lists(mock_bridge, action="create")
        assert "error" in result.lower() or "required" in result.lower()

    async def test_update_list(self, mock_bridge: AsyncMock) -> None:
        mock_bridge.send_command.return_value = make_success_response(
            {"id": "l1", "title": "Renamed", "count": 3}
        )
        result = await handle_reminders_lists(
            mock_bridge, action="update", id="l1", title="Renamed"
        )
        mock_bridge.send_command.assert_awaited_once_with(
            "update_list", {"id": "l1", "title": "Renamed"}
        )
        assert "Renamed" in result

    async def test_update_list_missing_id(self, mock_bridge: AsyncMock) -> None:
        result = await handle_reminders_lists(
            mock_bridge, action="update", title="New Name"
        )
        assert "error" in result.lower() or "required" in result.lower()

    async def test_update_list_missing_title(self, mock_bridge: AsyncMock) -> None:
        result = await handle_reminders_lists(
            mock_bridge, action="update", id="l1"
        )
        assert "error" in result.lower() or "required" in result.lower()

    async def test_delete_list(self, mock_bridge: AsyncMock) -> None:
        mock_bridge.send_command.return_value = make_success_response(None)
        result = await handle_reminders_lists(
            mock_bridge, action="delete", id="l1"
        )
        mock_bridge.send_command.assert_awaited_once_with("delete_list", {"id": "l1"})
        assert "deleted" in result.lower() or "success" in result.lower()

    async def test_delete_list_missing_id(self, mock_bridge: AsyncMock) -> None:
        result = await handle_reminders_lists(mock_bridge, action="delete")
        assert "error" in result.lower() or "required" in result.lower()

    async def test_bridge_error_propagates(self, mock_bridge: AsyncMock) -> None:
        mock_bridge.send_command.return_value = make_error_response("Permission denied")
        result = await handle_reminders_lists(mock_bridge, action="read")
        assert "Permission denied" in result
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_tools.py::TestRemindersLists -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'server.tools.reminders_lists'`

- [ ] **Step 4: Implement lists tool handler**

Create `server/tools/reminders_lists.py`:

```python
"""MCP tool for managing reminder lists."""

from __future__ import annotations

import json
from typing import Literal

from server.bridge.models import ReminderList
from server.bridge.swift_bridge import SwiftBridge


async def handle_reminders_lists(
    bridge: SwiftBridge,
    *,
    action: Literal["read", "create", "update", "delete"],
    id: str | None = None,
    title: str | None = None,
) -> str:
    """Execute a reminder lists action via the Swift bridge.

    Returns a JSON string for structured data or an error message.
    """
    match action:
        case "read":
            resp = await bridge.send_command("list_lists", {})
            if not resp.success:
                return f"Error: {resp.error}"
            lists = [ReminderList.model_validate(item) for item in resp.data]
            return json.dumps(
                [lst.model_dump() for lst in lists], indent=2, ensure_ascii=False
            )

        case "create":
            if not title:
                return "Error: 'title' is required for create action."
            resp = await bridge.send_command("create_list", {"title": title})
            if not resp.success:
                return f"Error: {resp.error}"
            created = ReminderList.model_validate(resp.data)
            return json.dumps(created.model_dump(), indent=2, ensure_ascii=False)

        case "update":
            if not id:
                return "Error: 'id' is required for update action."
            if not title:
                return "Error: 'title' is required for update action."
            resp = await bridge.send_command("update_list", {"id": id, "title": title})
            if not resp.success:
                return f"Error: {resp.error}"
            updated = ReminderList.model_validate(resp.data)
            return json.dumps(updated.model_dump(), indent=2, ensure_ascii=False)

        case "delete":
            if not id:
                return "Error: 'id' is required for delete action."
            resp = await bridge.send_command("delete_list", {"id": id})
            if not resp.success:
                return f"Error: {resp.error}"
            return json.dumps({"status": "deleted", "id": id}, ensure_ascii=False)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_tools.py::TestRemindersLists -v`
Expected: All 9 tests PASS

- [ ] **Step 6: Lint**

Run: `uv run ruff check server/tools/reminders_lists.py && uv run ruff format --check server/tools/reminders_lists.py`
Expected: No issues

- [ ] **Step 7: Commit**

```bash
git add server/tools/reminders_lists.py tests/conftest.py tests/test_tools.py
git commit -m "feat: add reminders_lists tool handler with CRUD actions"
```

---

## Task 7: Reminders Tasks Tool

**Files:**
- Create: `server/tools/reminders_tasks.py`
- Modify: `tests/test_tools.py` (add tasks tests)

- [ ] **Step 1: Write failing tests for tasks tool**

Append to `tests/test_tools.py`:

```python
from server.tools.reminders_tasks import handle_reminders_tasks


class TestRemindersTasks:
    async def test_read_all(self, mock_bridge: AsyncMock) -> None:
        mock_bridge.send_command.return_value = make_success_response(
            [
                {
                    "id": "r1",
                    "title": "Buy milk",
                    "list_id": "l1",
                    "list_title": "Shopping",
                    "is_completed": False,
                    "priority": 0,
                },
            ]
        )
        result = await handle_reminders_tasks(mock_bridge, action="read")
        mock_bridge.send_command.assert_awaited_once_with(
            "list_reminders",
            {"show_completed": False},
        )
        assert "Buy milk" in result

    async def test_read_with_filters(self, mock_bridge: AsyncMock) -> None:
        mock_bridge.send_command.return_value = make_success_response([])
        result = await handle_reminders_tasks(
            mock_bridge,
            action="read",
            filter_list="Shopping",
            show_completed=True,
            due_within="today",
            filter_priority="high",
            search="milk",
            filter_tags=["urgent"],
        )
        mock_bridge.send_command.assert_awaited_once_with(
            "list_reminders",
            {
                "list": "Shopping",
                "show_completed": True,
                "due_within": "today",
                "priority": "high",
                "search": "milk",
                "tags": ["urgent"],
            },
        )

    async def test_read_single_by_id(self, mock_bridge: AsyncMock) -> None:
        mock_bridge.send_command.return_value = make_success_response(
            {
                "id": "r1",
                "title": "Buy milk",
                "list_id": "l1",
                "list_title": "Shopping",
                "is_completed": False,
                "priority": 0,
            }
        )
        result = await handle_reminders_tasks(mock_bridge, action="read", id="r1")
        mock_bridge.send_command.assert_awaited_once_with(
            "get_reminder", {"id": "r1"}
        )
        assert "Buy milk" in result

    async def test_create_reminder(self, mock_bridge: AsyncMock) -> None:
        mock_bridge.send_command.return_value = make_success_response(
            {
                "id": "r2",
                "title": "Call dentist",
                "list_id": "l2",
                "list_title": "Health",
                "is_completed": False,
                "priority": 1,
                "due_date": "2026-03-20T09:00:00Z",
            }
        )
        result = await handle_reminders_tasks(
            mock_bridge,
            action="create",
            title="Call dentist",
            target_list="Health",
            priority=1,
            due_date="2026-03-20T09:00:00Z",
            note="Annual checkup",
            tags=["health"],
        )
        call_params = mock_bridge.send_command.call_args[0][1]
        assert call_params["title"] == "Call dentist"
        assert call_params["list"] == "Health"
        assert call_params["priority"] == 1
        assert "Call dentist" in result

    async def test_create_missing_title(self, mock_bridge: AsyncMock) -> None:
        result = await handle_reminders_tasks(mock_bridge, action="create")
        assert "error" in result.lower() or "required" in result.lower()

    async def test_update_reminder(self, mock_bridge: AsyncMock) -> None:
        mock_bridge.send_command.return_value = make_success_response(
            {
                "id": "r1",
                "title": "Buy oat milk",
                "list_id": "l1",
                "list_title": "Shopping",
                "is_completed": False,
                "priority": 0,
            }
        )
        result = await handle_reminders_tasks(
            mock_bridge,
            action="update",
            id="r1",
            title="Buy oat milk",
            completed=True,
        )
        call_params = mock_bridge.send_command.call_args[0][1]
        assert call_params["id"] == "r1"
        assert call_params["title"] == "Buy oat milk"
        assert call_params["completed"] is True

    async def test_update_missing_id(self, mock_bridge: AsyncMock) -> None:
        result = await handle_reminders_tasks(
            mock_bridge, action="update", title="New"
        )
        assert "error" in result.lower() or "required" in result.lower()

    async def test_delete_reminder(self, mock_bridge: AsyncMock) -> None:
        mock_bridge.send_command.return_value = make_success_response(None)
        result = await handle_reminders_tasks(
            mock_bridge, action="delete", id="r1"
        )
        mock_bridge.send_command.assert_awaited_once_with(
            "delete_reminder", {"id": "r1"}
        )
        assert "deleted" in result.lower() or "success" in result.lower()

    async def test_delete_missing_id(self, mock_bridge: AsyncMock) -> None:
        result = await handle_reminders_tasks(mock_bridge, action="delete")
        assert "error" in result.lower() or "required" in result.lower()

    async def test_bridge_error(self, mock_bridge: AsyncMock) -> None:
        mock_bridge.send_command.return_value = make_error_response("Timeout")
        result = await handle_reminders_tasks(mock_bridge, action="read")
        assert "Timeout" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tools.py::TestRemindersTasks -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'server.tools.reminders_tasks'`

- [ ] **Step 3: Implement tasks tool handler**

Create `server/tools/reminders_tasks.py`:

```python
"""MCP tool for managing reminder tasks."""

from __future__ import annotations

import json
from typing import Literal

from server.bridge.models import Reminder
from server.bridge.swift_bridge import SwiftBridge


async def handle_reminders_tasks(
    bridge: SwiftBridge,
    *,
    action: Literal["read", "create", "update", "delete"],
    id: str | None = None,
    title: str | None = None,
    filter_list: str | None = None,
    show_completed: bool = False,
    search: str | None = None,
    due_within: Literal["today", "tomorrow", "this-week", "overdue", "no-date"] | None = None,
    filter_priority: Literal["high", "medium", "low", "none"] | None = None,
    filter_tags: list[str] | None = None,
    due_date: str | None = None,
    note: str | None = None,
    url: str | None = None,
    priority: int | None = None,
    completed: bool | None = None,
    target_list: str | None = None,
    tags: list[str] | None = None,
    subtasks: list[str] | None = None,
    recurrence: str | None = None,
    location_trigger: str | None = None,
    alarms: list[str] | None = None,
) -> str:
    """Execute a reminder tasks action via the Swift bridge."""
    match action:
        case "read":
            if id:
                resp = await bridge.send_command("get_reminder", {"id": id})
                if not resp.success:
                    return f"Error: {resp.error}"
                reminder = Reminder.model_validate(resp.data)
                return json.dumps(
                    reminder.model_dump(), indent=2, ensure_ascii=False
                )

            params: dict[str, object] = {"show_completed": show_completed}
            if filter_list:
                params["list"] = filter_list
            if search:
                params["search"] = search
            if due_within:
                params["due_within"] = due_within
            if filter_priority:
                params["priority"] = filter_priority
            if filter_tags:
                params["tags"] = filter_tags

            resp = await bridge.send_command("list_reminders", params)
            if not resp.success:
                return f"Error: {resp.error}"
            reminders = [Reminder.model_validate(item) for item in resp.data]
            return json.dumps(
                [r.model_dump() for r in reminders], indent=2, ensure_ascii=False
            )

        case "create":
            if not title:
                return "Error: 'title' is required for create action."
            params = {"title": title}
            if target_list:
                params["list"] = target_list
            if due_date:
                params["due_date"] = due_date
            if note:
                params["note"] = note
            if url:
                params["url"] = url
            if priority is not None:
                params["priority"] = priority
            if tags:
                params["tags"] = tags
            if subtasks:
                params["subtasks"] = subtasks
            if recurrence:
                params["recurrence"] = recurrence
            if location_trigger:
                params["location_trigger"] = location_trigger
            if alarms:
                params["alarms"] = alarms

            resp = await bridge.send_command("create_reminder", params)
            if not resp.success:
                return f"Error: {resp.error}"
            created = Reminder.model_validate(resp.data)
            return json.dumps(
                created.model_dump(), indent=2, ensure_ascii=False
            )

        case "update":
            if not id:
                return "Error: 'id' is required for update action."
            params = {"id": id}
            if title is not None:
                params["title"] = title
            if due_date is not None:
                params["due_date"] = due_date
            if note is not None:
                params["note"] = note
            if url is not None:
                params["url"] = url
            if priority is not None:
                params["priority"] = priority
            if completed is not None:
                params["completed"] = completed
            if target_list is not None:
                params["list"] = target_list
            if tags is not None:
                params["tags"] = tags
            if recurrence is not None:
                params["recurrence"] = recurrence
            if location_trigger is not None:
                params["location_trigger"] = location_trigger
            if alarms is not None:
                params["alarms"] = alarms

            resp = await bridge.send_command("update_reminder", params)
            if not resp.success:
                return f"Error: {resp.error}"
            updated = Reminder.model_validate(resp.data)
            return json.dumps(
                updated.model_dump(), indent=2, ensure_ascii=False
            )

        case "delete":
            if not id:
                return "Error: 'id' is required for delete action."
            resp = await bridge.send_command("delete_reminder", {"id": id})
            if not resp.success:
                return f"Error: {resp.error}"
            return json.dumps(
                {"status": "deleted", "id": id}, ensure_ascii=False
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_tools.py::TestRemindersTasks -v`
Expected: All 10 tests PASS

- [ ] **Step 5: Lint**

Run: `uv run ruff check server/tools/reminders_tasks.py && uv run ruff format --check server/tools/reminders_tasks.py`
Expected: No issues

- [ ] **Step 6: Commit**

```bash
git add server/tools/reminders_tasks.py tests/test_tools.py
git commit -m "feat: add reminders_tasks tool handler with filters and CRUD"
```

---

## Task 8: Reminders Subtasks Tool

**Files:**
- Create: `server/tools/reminders_subtasks.py`
- Modify: `tests/test_tools.py` (add subtasks tests)

- [ ] **Step 1: Write failing tests for subtasks tool**

Append to `tests/test_tools.py`:

```python
from server.tools.reminders_subtasks import handle_reminders_subtasks


class TestRemindersSubtasks:
    async def test_read_subtasks(self, mock_bridge: AsyncMock) -> None:
        mock_bridge.send_command.return_value = make_success_response(
            [
                {"id": "s1", "title": "Pick up rx", "is_completed": False},
                {"id": "s2", "title": "Call pharmacy", "is_completed": True},
            ]
        )
        result = await handle_reminders_subtasks(
            mock_bridge, action="read", reminder_id="r1"
        )
        mock_bridge.send_command.assert_awaited_once_with(
            "list_subtasks", {"reminder_id": "r1"}
        )
        assert "Pick up rx" in result

    async def test_read_missing_reminder_id(self, mock_bridge: AsyncMock) -> None:
        result = await handle_reminders_subtasks(mock_bridge, action="read")
        assert "error" in result.lower() or "required" in result.lower()

    async def test_create_subtask(self, mock_bridge: AsyncMock) -> None:
        mock_bridge.send_command.return_value = make_success_response(
            {"id": "s3", "title": "New subtask", "is_completed": False}
        )
        result = await handle_reminders_subtasks(
            mock_bridge,
            action="create",
            reminder_id="r1",
            title="New subtask",
        )
        call_params = mock_bridge.send_command.call_args[0][1]
        assert call_params["reminder_id"] == "r1"
        assert call_params["title"] == "New subtask"

    async def test_create_missing_title(self, mock_bridge: AsyncMock) -> None:
        result = await handle_reminders_subtasks(
            mock_bridge, action="create", reminder_id="r1"
        )
        assert "error" in result.lower() or "required" in result.lower()

    async def test_update_subtask(self, mock_bridge: AsyncMock) -> None:
        mock_bridge.send_command.return_value = make_success_response(
            {"id": "s1", "title": "Updated", "is_completed": True}
        )
        result = await handle_reminders_subtasks(
            mock_bridge,
            action="update",
            reminder_id="r1",
            id="s1",
            title="Updated",
            completed=True,
        )
        call_params = mock_bridge.send_command.call_args[0][1]
        assert call_params["id"] == "s1"

    async def test_delete_subtask(self, mock_bridge: AsyncMock) -> None:
        mock_bridge.send_command.return_value = make_success_response(None)
        result = await handle_reminders_subtasks(
            mock_bridge, action="delete", reminder_id="r1", id="s1"
        )
        mock_bridge.send_command.assert_awaited_once_with(
            "delete_subtask", {"reminder_id": "r1", "id": "s1"}
        )

    async def test_delete_subtask_missing_id(self, mock_bridge: AsyncMock) -> None:
        result = await handle_reminders_subtasks(
            mock_bridge, action="delete", reminder_id="r1"
        )
        assert "error" in result.lower() or "required" in result.lower()

    async def test_toggle_subtask(self, mock_bridge: AsyncMock) -> None:
        mock_bridge.send_command.return_value = make_success_response(
            {"id": "s1", "title": "Toggle me", "is_completed": True}
        )
        result = await handle_reminders_subtasks(
            mock_bridge, action="toggle", reminder_id="r1", id="s1"
        )
        mock_bridge.send_command.assert_awaited_once_with(
            "toggle_subtask", {"reminder_id": "r1", "id": "s1"}
        )

    async def test_toggle_subtask_missing_id(self, mock_bridge: AsyncMock) -> None:
        result = await handle_reminders_subtasks(
            mock_bridge, action="toggle", reminder_id="r1"
        )
        assert "error" in result.lower() or "required" in result.lower()

    async def test_reorder_subtasks(self, mock_bridge: AsyncMock) -> None:
        mock_bridge.send_command.return_value = make_success_response(None)
        result = await handle_reminders_subtasks(
            mock_bridge,
            action="reorder",
            reminder_id="r1",
            order=["s2", "s1", "s3"],
        )
        call_params = mock_bridge.send_command.call_args[0][1]
        assert call_params["order"] == ["s2", "s1", "s3"]

    async def test_reorder_missing_order(self, mock_bridge: AsyncMock) -> None:
        result = await handle_reminders_subtasks(
            mock_bridge, action="reorder", reminder_id="r1"
        )
        assert "error" in result.lower() or "required" in result.lower()

    async def test_bridge_error(self, mock_bridge: AsyncMock) -> None:
        mock_bridge.send_command.return_value = make_error_response("Not found")
        result = await handle_reminders_subtasks(
            mock_bridge, action="read", reminder_id="r1"
        )
        assert "Not found" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tools.py::TestRemindersSubtasks -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'server.tools.reminders_subtasks'`

- [ ] **Step 3: Implement subtasks tool handler**

Create `server/tools/reminders_subtasks.py`:

```python
"""MCP tool for managing reminder subtasks."""

from __future__ import annotations

import json
from typing import Literal

from server.bridge.models import Subtask
from server.bridge.swift_bridge import SwiftBridge


async def handle_reminders_subtasks(
    bridge: SwiftBridge,
    *,
    action: Literal["read", "create", "update", "delete", "toggle", "reorder"],
    reminder_id: str | None = None,
    id: str | None = None,
    title: str | None = None,
    completed: bool | None = None,
    order: list[str] | None = None,
) -> str:
    """Execute a subtask action via the Swift bridge."""
    if not reminder_id:
        return "Error: 'reminder_id' is required for all subtask actions."

    match action:
        case "read":
            resp = await bridge.send_command(
                "list_subtasks", {"reminder_id": reminder_id}
            )
            if not resp.success:
                return f"Error: {resp.error}"
            subtasks = [Subtask.model_validate(item) for item in resp.data]
            return json.dumps(
                [s.model_dump() for s in subtasks], indent=2, ensure_ascii=False
            )

        case "create":
            if not title:
                return "Error: 'title' is required for create action."
            resp = await bridge.send_command(
                "create_subtask", {"reminder_id": reminder_id, "title": title}
            )
            if not resp.success:
                return f"Error: {resp.error}"
            created = Subtask.model_validate(resp.data)
            return json.dumps(created.model_dump(), indent=2, ensure_ascii=False)

        case "update":
            if not id:
                return "Error: 'id' is required for update action."
            params: dict[str, object] = {"reminder_id": reminder_id, "id": id}
            if title is not None:
                params["title"] = title
            if completed is not None:
                params["completed"] = completed
            resp = await bridge.send_command("update_subtask", params)
            if not resp.success:
                return f"Error: {resp.error}"
            updated = Subtask.model_validate(resp.data)
            return json.dumps(updated.model_dump(), indent=2, ensure_ascii=False)

        case "delete":
            if not id:
                return "Error: 'id' is required for delete action."
            resp = await bridge.send_command(
                "delete_subtask", {"reminder_id": reminder_id, "id": id}
            )
            if not resp.success:
                return f"Error: {resp.error}"
            return json.dumps(
                {"status": "deleted", "id": id}, ensure_ascii=False
            )

        case "toggle":
            if not id:
                return "Error: 'id' is required for toggle action."
            resp = await bridge.send_command(
                "toggle_subtask", {"reminder_id": reminder_id, "id": id}
            )
            if not resp.success:
                return f"Error: {resp.error}"
            toggled = Subtask.model_validate(resp.data)
            return json.dumps(toggled.model_dump(), indent=2, ensure_ascii=False)

        case "reorder":
            if not order:
                return "Error: 'order' is required for reorder action."
            resp = await bridge.send_command(
                "reorder_subtasks", {"reminder_id": reminder_id, "order": order}
            )
            if not resp.success:
                return f"Error: {resp.error}"
            return json.dumps(
                {"status": "reordered", "reminder_id": reminder_id},
                ensure_ascii=False,
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_tools.py::TestRemindersSubtasks -v`
Expected: All 12 tests PASS

- [ ] **Step 5: Lint**

Run: `uv run ruff check server/tools/reminders_subtasks.py && uv run ruff format --check server/tools/reminders_subtasks.py`
Expected: No issues

- [ ] **Step 6: Commit**

```bash
git add server/tools/reminders_subtasks.py tests/test_tools.py
git commit -m "feat: add reminders_subtasks tool handler with toggle and reorder"
```

---

## Task 9: Register MCP Tools on FastMCP

**Files:**
- Modify: `server/tools/reminders_lists.py` (add `@mcp.tool()` wrapper)
- Modify: `server/tools/reminders_tasks.py` (add `@mcp.tool()` wrapper)
- Modify: `server/tools/reminders_subtasks.py` (add `@mcp.tool()` wrapper)

This task adds `@mcp.tool()` decorated wrapper functions to each tool file. They import `mcp` and `get_bridge` from `server.mcp_instance` (NOT from `server.app`) to avoid circular imports.

- [ ] **Step 1: Add `@mcp.tool()` registration to `server/tools/reminders_lists.py`**

Add at the **top** of the file, after imports:

```python
from server.mcp_instance import get_bridge, mcp
```

Add at the **bottom** of the file:

```python
@mcp.tool()
async def reminders_lists(
    action: Literal["read", "create", "update", "delete"],
    id: str | None = None,
    title: str | None = None,
) -> str:
    """Manage reminder lists.

    Actions:
    - read: List all reminder lists
    - create: Create a new list (requires: title)
    - update: Rename a list (requires: id, title)
    - delete: Delete a list (requires: id)
    """
    bridge = get_bridge()
    return await handle_reminders_lists(bridge, action=action, id=id, title=title)
```

- [ ] **Step 2: Add `@mcp.tool()` registration to `server/tools/reminders_tasks.py`**

Add at the **top** of the file, after imports:

```python
from server.mcp_instance import get_bridge, mcp
```

Add at the **bottom** of the file:

```python
@mcp.tool()
async def reminders_tasks(
    action: Literal["read", "create", "update", "delete"],
    id: str | None = None,
    title: str | None = None,
    filter_list: str | None = None,
    show_completed: bool = False,
    search: str | None = None,
    due_within: Literal["today", "tomorrow", "this-week", "overdue", "no-date"] | None = None,
    filter_priority: Literal["high", "medium", "low", "none"] | None = None,
    filter_tags: list[str] | None = None,
    due_date: str | None = None,
    note: str | None = None,
    url: str | None = None,
    priority: int | None = None,
    completed: bool | None = None,
    target_list: str | None = None,
    tags: list[str] | None = None,
    subtasks: list[str] | None = None,
    recurrence: str | None = None,
    location_trigger: str | None = None,
    alarms: list[str] | None = None,
) -> str:
    """Manage reminder tasks.

    Actions:
    - read: List reminders (optional filters: filter_list, show_completed, search, due_within, filter_priority, filter_tags) or get one by id
    - create: Create a reminder (requires: title; optional: target_list, due_date, note, url, priority, tags, subtasks, recurrence, location_trigger, alarms)
    - update: Update a reminder (requires: id; optional: any field to change)
    - delete: Delete a reminder (requires: id)

    Priority values: 0=none, 1=high, 5=medium, 9=low
    Dates: ISO 8601 format (e.g., "2026-03-20T09:00:00Z")
    """
    bridge = get_bridge()
    return await handle_reminders_tasks(
        bridge,
        action=action,
        id=id,
        title=title,
        filter_list=filter_list,
        show_completed=show_completed,
        search=search,
        due_within=due_within,
        filter_priority=filter_priority,
        filter_tags=filter_tags,
        due_date=due_date,
        note=note,
        url=url,
        priority=priority,
        completed=completed,
        target_list=target_list,
        tags=tags,
        subtasks=subtasks,
        recurrence=recurrence,
        location_trigger=location_trigger,
        alarms=alarms,
    )
```

- [ ] **Step 3: Add `@mcp.tool()` registration to `server/tools/reminders_subtasks.py`**

Add at the **top** of the file, after imports:

```python
from server.mcp_instance import get_bridge, mcp
```

Add at the **bottom** of the file:

```python
@mcp.tool()
async def reminders_subtasks(
    action: Literal["read", "create", "update", "delete", "toggle", "reorder"],
    reminder_id: str | None = None,
    id: str | None = None,
    title: str | None = None,
    completed: bool | None = None,
    order: list[str] | None = None,
) -> str:
    """Manage subtasks within a reminder.

    Actions:
    - read: List subtasks for a reminder (requires: reminder_id)
    - create: Add a subtask (requires: reminder_id, title)
    - update: Modify a subtask (requires: reminder_id, id)
    - delete: Remove a subtask (requires: reminder_id, id)
    - toggle: Toggle subtask completion (requires: reminder_id, id)
    - reorder: Reorder subtasks (requires: reminder_id, order)
    """
    bridge = get_bridge()
    return await handle_reminders_subtasks(
        bridge,
        action=action,
        reminder_id=reminder_id,
        id=id,
        title=title,
        completed=completed,
        order=order,
    )
```

- [ ] **Step 4: Verify imports work and tools are registered**

Run: `uv run python -c "from server.app import create_asgi_app; from server.mcp_instance import mcp; print(len(mcp._tool_manager._tools), 'tools registered')"`
Expected: Prints `3 tools registered`

- [ ] **Step 5: Lint all modified files**

Run: `uv run ruff check server/ && uv run ruff format --check server/`
Expected: No issues

- [ ] **Step 6: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests PASS (40+ tests)

- [ ] **Step 7: Commit**

```bash
git add server/tools/reminders_lists.py server/tools/reminders_tasks.py server/tools/reminders_subtasks.py
git commit -m "feat: wire up MCP tool registration on FastMCP instance"
```

---

## Task 10: Full Lint, Type-Check, and Final Verification

**Files:**
- No new files — verification only

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest -v --tb=short`
Expected: All tests PASS

- [ ] **Step 2: Run ruff linting**

Run: `uv run ruff check .`
Expected: No issues

- [ ] **Step 3: Run ruff format check**

Run: `uv run ruff format --check .`
Expected: No issues

- [ ] **Step 4: Run mypy type-checking**

Run: `uv run python -m mypy server/`
Expected: No errors (or only expected warnings about third-party stubs)

Note: If mypy complains about missing stubs for `mcp` or `dotenv`, add to `pyproject.toml`:
```toml
[tool.mypy]
# ... existing config ...
[[tool.mypy.overrides]]
module = ["mcp.*", "dotenv"]
ignore_missing_imports = true
```

- [ ] **Step 5: Fix any issues found**

Fix any lint/type/test issues discovered in steps 1-4.

- [ ] **Step 6: Commit fixes if any**

```bash
git add -u
git commit -m "chore: fix lint and type-check issues"
```

---

## Summary

| Task | What it builds | Tests |
|------|---------------|-------|
| 1 | Project scaffolding (pyproject.toml, packages) | Setup verification |
| 2 | Pydantic bridge models | 9 tests |
| 3 | SwiftBridge async client | 4 tests |
| 4 | Bearer auth middleware | 6 tests |
| 5 | mcp_instance.py + app.py + entry point | Import verification |
| 6 | reminders_lists tool | 9 tests |
| 7 | reminders_tasks tool | 10 tests |
| 8 | reminders_subtasks tool | 12 tests |
| 9 | MCP tool registration wiring | Integration verification |
| 10 | Full lint + type-check pass | All tests |

**Total: ~50 tests, 10 tasks, ~16 files created**

**Follow-up plans (separate, macOS-only):**
- Swift EventKit bridge (`swift-bridge/`)
- Deployment scripts and Cloudflare Tunnel config (`scripts/`, `tunnel/`, `docs/`)
