# Apple Reminders Remote MCP Server

Cross-platform MCP server for Apple Reminders. Python server runs on a home macOS machine (accessing EventKit via a Swift CLI bridge), exposed to the internet via Cloudflare Tunnel, consumed as a remote MCP server from anywhere — Windows office, phone, etc.

## Architecture

```
┌──────────────────────────┐                                    ┌──────────────────────────────────────────┐
│  Windows (office)        │      HTTPS (internet)              │  macOS at home                           │
│  Claude Code             │  ◄──────────────────────────────►  │                                          │
│                          │                                    │  cloudflared ──► localhost:8000           │
│  claude mcp add          │                                    │                    │                      │
│    --transport http      │                                    │              FastMCP server (Python)      │
│    reminders             │                                    │                    │                      │
│    https://reminders     │                                    │              Swift CLI (EventKitCLI)      │
│      .yourdomain.com/mcp │                                    │                    │                      │
│                          │                                    │              Apple Reminders (EventKit)   │
└──────────────────────────┘                                    └──────────────────────────────────────────┘
                                         │
                                    Cloudflare Tunnel
                                    (outbound-only from Mac,
                                     HTTPS + DDoS protection,
                                     no port forwarding needed)
```

Two components in the **same repo**:

1. **`server/`** — Python MCP server using `mcp` SDK (`FastMCP`) with Streamable HTTP transport. Runs on macOS at home. Calls the Swift CLI bridge to interact with Apple Reminders.
2. **`swift-bridge/`** — Swift CLI binary (`EventKitCLI`) that wraps EventKit framework. Compiled and runs exclusively on macOS. The Python server spawns it as a subprocess and communicates via JSON over stdin/stdout.

There is NO separate "client" package — Claude Code connects directly to the server's HTTPS endpoint via Cloudflare Tunnel.

## Tech Stack

- Python 3.12+
- `uv` — package manager and virtual environment
- `mcp` SDK (latest, the official `mcp` package on PyPI) — provides `FastMCP`, Streamable HTTP transport
- `pydantic` — data models and validation (used by FastMCP internally)
- `uvicorn` — ASGI server (used by FastMCP under the hood)
- `httpx` — async HTTP client (if needed for health checks)
- Swift 5.9+ — EventKit bridge CLI (macOS only)
- `cloudflared` — Cloudflare Tunnel daemon (runs on macOS alongside the server)
- `ruff` — linting and formatting
- `pytest` + `pytest-asyncio` — testing

## Project Structure

```
/
├── CLAUDE.md
├── pyproject.toml          # uv/pip project config, all deps here
├── uv.lock
├── .env.example            # REMINDERS_API_TOKEN, PORT, HOST, CF_TUNNEL_TOKEN
├── .python-version         # 3.12
│
├── server/
│   ├── __init__.py
│   ├── __main__.py         # Entry point: `python -m server`
│   ├── app.py              # FastMCP instance creation and tool registration
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── reminders_tasks.py      # CRUD for reminder items
│   │   ├── reminders_lists.py      # CRUD for reminder lists
│   │   └── reminders_subtasks.py   # Subtask management
│   ├── bridge/
│   │   ├── __init__.py
│   │   ├── swift_bridge.py         # Spawns EventKitCLI, sends JSON commands, parses responses
│   │   └── models.py               # Pydantic models matching Swift CLI JSON schema
│   └── auth.py                     # Bearer token auth middleware (ASGI middleware)
│
├── swift-bridge/
│   ├── Package.swift
│   ├── Sources/
│   │   └── EventKitCLI/
│   │       ├── main.swift          # CLI entry: reads JSON from stdin, dispatches commands
│   │       ├── ReminderService.swift
│   │       ├── ListService.swift
│   │       └── Models.swift        # Codable structs matching Python models
│   └── build.sh                    # Compiles the Swift binary
│
├── scripts/
│   ├── build-swift.sh              # Compile Swift binary
│   ├── setup-tunnel.sh             # Cloudflare Tunnel setup helper
│   ├── start.sh                    # Start server + cloudflared together
│   ├── check-permissions.sh        # Verify macOS EventKit permissions
│   └── install-service.sh          # Install both server + cloudflared as macOS launch agents
│
├── tunnel/
│   ├── config.yml.example          # Cloudflare Tunnel config template
│   ├── com.reminders-mcp.server.plist.example    # launchd plist for the MCP server
│   └── com.reminders-mcp.tunnel.plist.example    # launchd plist for cloudflared
│
├── tests/
│   ├── conftest.py
│   ├── test_tools.py               # Tool handlers with mocked Swift bridge
│   ├── test_bridge.py              # Swift bridge integration (macOS only)
│   └── test_auth.py                # Auth middleware tests
│
└── docs/
    └── setup.md                    # End-to-end setup guide
```

## Commands

- `uv sync` — install all deps into venv
- `uv run python -m server` — start MCP server (dev mode)
- `uv run python -m server --reload` — start with auto-reload on file changes
- `./scripts/build-swift.sh` — compile Swift binary (`swift build -c release`)
- `./scripts/start.sh` — start both MCP server and cloudflared tunnel
- `./scripts/install-service.sh` — install as macOS launch agents (auto-start on boot)
- `uv run pytest` — run tests
- `uv run ruff check .` — lint
- `uv run ruff format .` — format
- `uv run ruff check . && uv run ruff format --check . && uv run python -m mypy server/` — full check

## Code Style

- Python 3.12+, use modern syntax: `type X = ...` aliases, `match` statements, `|` unions
- Type hints everywhere, run `mypy` in strict mode
- Async functions for all tool handlers (FastMCP is async-native)
- Pydantic v2 models for all data structures
- Ruff for formatting (88 char line length, double quotes) and linting
- No `print()` for logging — use `logging` module or FastMCP's built-in logging
- Errors: always return structured MCP error responses, never raise unhandled exceptions in tool handlers

## Key Implementation Details

### FastMCP with Streamable HTTP Transport

This server MUST use Streamable HTTP transport. The whole point is remote access over the internet.

```python
# server/app.py — skeleton
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "apple-reminders-remote",
    stateless_http=True,        # No session state — simpler, works behind load balancers
    host="127.0.0.1",           # Bind to localhost ONLY — cloudflared handles external access
    port=8000,
    json_response=True,         # Recommended for production
)

# Tools are registered via @mcp.tool() decorators in server/tools/*.py
# Import them to trigger registration:
from server.tools import reminders_tasks, reminders_lists, reminders_subtasks

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
```

**Critical**: Bind to `127.0.0.1` (NOT `0.0.0.0`), because Cloudflare Tunnel provides external access. No direct port exposure needed.

### Swift Bridge Communication Protocol

The Swift CLI (`EventKitCLI`) uses a JSON-over-stdin/stdout protocol:

- **Input** (stdin): one JSON object per line — `{ "id": "req-uuid", "command": "...", "params": {...} }`
- **Output** (stdout): one JSON response per line — `{ "id": "req-uuid", "success": true, "data": ... }` or `{ "id": "req-uuid", "success": false, "error": "..." }`
- **Stderr**: logging only, never parsed

The Python bridge (`server/bridge/swift_bridge.py`) spawns the Swift binary once at startup using `asyncio.create_subprocess_exec`, keeps it alive, and sends commands as newline-delimited JSON. Use `id` field (UUID4) for request-response correlation since multiple requests may be in flight.

Commands to implement in Swift:

| Command | Description |
|---|---|
| `list_lists` | Return all reminder lists |
| `create_list` | Create a new list |
| `update_list` | Rename a list |
| `delete_list` | Delete a list |
| `list_reminders` | Read reminders with filters (list, completed, search, dueWithin, priority, tags) |
| `get_reminder` | Get single reminder by ID |
| `create_reminder` | Create reminder with full field support (title, notes, dueDate, priority, tags, subtasks, recurrence, location trigger, alarms, URL) |
| `update_reminder` | Update any reminder fields |
| `delete_reminder` | Delete a reminder |
| `list_subtasks` | List subtasks for a reminder |
| `create_subtask` | Add subtask |
| `update_subtask` | Modify subtask |
| `delete_subtask` | Remove subtask |
| `toggle_subtask` | Toggle subtask completion |
| `reorder_subtasks` | Reorder subtasks |

### MCP Tool Design

Follow the action-based pattern — each tool accepts an `action` parameter. Three tools total:

```python
from mcp.server.fastmcp import FastMCP
from typing import Literal

@mcp.tool()
async def reminders_tasks(
    action: Literal["read", "create", "update", "delete"],
    # Conditional params — all optional, validated per action in the handler body
    id: str | None = None,
    title: str | None = None,
    filter_list: str | None = None,
    show_completed: bool = False,
    search: str | None = None,
    due_within: Literal["today", "tomorrow", "this-week", "overdue", "no-date"] | None = None,
    filter_priority: Literal["high", "medium", "low", "none"] | None = None,
    due_date: str | None = None,
    note: str | None = None,
    url: str | None = None,
    priority: int | None = None,   # 0=none, 1=high, 5=medium, 9=low
    completed: bool | None = None,
    target_list: str | None = None,
    tags: list[str] | None = None,
    subtasks: list[str] | None = None,
    # ... recurrence, location_trigger, alarms
) -> str:
    """Manage reminder tasks. Actions: read, create, update, delete."""
    ...
```

### Authentication

Bearer token auth. Since FastMCP runs on Starlette/ASGI, use ASGI middleware to validate the token on the MCP endpoint:

```python
# server/auth.py
import os
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

class BearerAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/mcp"):
            token = request.headers.get("authorization", "").removeprefix("Bearer ")
            if token != os.environ["REMINDERS_API_TOKEN"]:
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
        return await call_next(request)
```

Apply it to the ASGI app. Check FastMCP docs for how to access the underlying Starlette app to add middleware — it may be `mcp.streamable_http_app()` which returns a Starlette app you can wrap.

### Internet Access via Cloudflare Tunnel

This is the core of the "access from anywhere" setup. Cloudflare Tunnel creates an outbound-only encrypted connection from the Mac to Cloudflare's edge. No port forwarding, no dynamic DNS, no exposed IP.

**Prerequisites**:
- A domain added to Cloudflare (free plan works). Can use an existing domain from nic.ua — just change NS to Cloudflare.
- `cloudflared` installed on macOS (`brew install cloudflared`)

**Setup** (one-time, documented in `docs/setup.md` and scripted in `scripts/setup-tunnel.sh`):

```bash
# 1. Authenticate
cloudflared tunnel login

# 2. Create a named tunnel
cloudflared tunnel create apple-reminders

# 3. Configure routing — tunnel/config.yml
# tunnel: <TUNNEL_UUID>
# credentials-file: ~/.cloudflared/<TUNNEL_UUID>.json
# ingress:
#   - hostname: reminders.yourdomain.com
#     service: http://localhost:8000
#   - service: http_status:404

# 4. Create DNS record
cloudflared tunnel route dns apple-reminders reminders.yourdomain.com

# 5. Run the tunnel
cloudflared tunnel run apple-reminders
```

**Production: run as macOS launch agents** (auto-starts on login, survives reboots):

The `scripts/install-service.sh` should install two launch agents:

1. **MCP Server** — `~/Library/LaunchAgents/com.reminders-mcp.server.plist`
   - WorkingDirectory: project root
   - ProgramArguments: path to `uv`, `run`, `python`, `-m`, `server`
   - EnvironmentVariables: `REMINDERS_API_TOKEN`, `PATH` (must include uv and swift)
   - RunAtLoad: true
   - KeepAlive: true
   - StandardOutPath / StandardErrorPath: `~/Library/Logs/reminders-mcp-server.log`

2. **Cloudflare Tunnel** — `~/Library/LaunchAgents/com.reminders-mcp.tunnel.plist`
   - ProgramArguments: path to `cloudflared`, `tunnel`, `run`, `apple-reminders`
   - RunAtLoad: true
   - KeepAlive: true
   - StandardOutPath / StandardErrorPath: `~/Library/Logs/reminders-mcp-tunnel.log`

Provide example plists in `tunnel/` directory.

### Swift Bridge: EventKit Permissions

The Swift CLI needs these Info.plist keys:
- `NSRemindersFullAccessUsageDescription`
- `NSRemindersUsageDescription`

On first run, macOS prompts for Reminders access. Include `check-permissions.sh` to verify. If denied, Swift CLI returns error JSON, MCP tool surfaces it.

**Important**: the Mac must have a logged-in user session for EventKit to work. Enable auto-login in System Settings so the Mac can run headless at home.

## Important Constraints

- Server + Swift bridge MUST run on macOS. EventKit has no cross-platform equivalent.
- Server binds to `127.0.0.1` only — external access exclusively through Cloudflare Tunnel.
- Handle Swift binary not compiled — check on startup, clear error pointing to `./scripts/build-swift.sh`.
- All dates in ISO 8601 between Python and Swift. Swift converts to/from EventKit native dates.
- Reminder IDs from EventKit are opaque strings (`calendarItemIdentifier`). Pass through as-is.
- Tags stored in notes field using `[#tag]` format for native Reminders app compatibility.
- Subtasks stored in notes using `---SUBTASKS---` / `---END SUBTASKS---` markers.
- Full UTF-8 support — titles, notes, tags may be in Ukrainian or other languages.
- Mac must be powered on, logged in (auto-login), and have internet for tunnel to function.
- If Mac loses internet temporarily, cloudflared reconnects automatically when connection restores.

## Testing Strategy

- **Unit tests** (`pytest`): tool handlers with a mocked Swift bridge
- **Integration tests** (`pytest`, macOS only): Swift bridge → real EventKit
- **Manual testing**: use MCP Inspector (`npx @modelcontextprotocol/inspector`) pointed at `http://localhost:8000/mcp` locally, or at `https://reminders.yourdomain.com/mcp` remotely
- **Tunnel health**: `curl -H "Authorization: Bearer <token>" https://reminders.yourdomain.com/mcp` — should get valid MCP response

## Workflow

- After Python changes: `uv run ruff check . && uv run ruff format --check .`
- After Swift changes: `./scripts/build-swift.sh` then `uv run pytest tests/test_bridge.py`
- Test full stack with MCP Inspector before committing
- Keep Swift binary in `.gitignore` — compiled on target macOS machine
- Keep `.env`, tunnel credentials, and `*.plist` (with real tokens) in `.gitignore`

## Client Configuration (from Windows office or anywhere)

After the server and tunnel are running on macOS at home:

```bash
claude mcp add --transport http apple-reminders https://reminders.yourdomain.com/mcp \
  --header "Authorization: Bearer <your-token>" \
  --scope user
```

Or in `.mcp.json`:

```json
{
  "mcpServers": {
    "apple-reminders": {
      "type": "http",
      "url": "https://reminders.yourdomain.com/mcp",
      "headers": {
        "Authorization": "Bearer <your-token>"
      }
    }
  }
}
```

## Skills

When implementing MCP tools or server infrastructure, use the `mcp-builder` skill for SDK patterns and best practices.

## Security Checklist

- [ ] Server binds to `127.0.0.1` only
- [ ] Bearer token auth on all `/mcp` routes
- [ ] Token stored in `.env`, never committed
- [ ] Cloudflare Tunnel credentials in `.gitignore`
- [ ] Consider enabling Cloudflare Access on top of tunnel for zero-trust auth layer
- [ ] Rate limiting via Cloudflare WAF rules (free tier includes basic rules)
- [ ] Monitor tunnel health via Cloudflare dashboard
- [ ] Mac auto-login enabled, Energy Saver set to prevent sleep