# Apple Reminders Remote MCP

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

## Mac Setup (Server Host)

### Prerequisites

- macOS with Apple Reminders
- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- Xcode Command Line Tools (for Swift bridge)
- A domain on Cloudflare (free plan works)

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install cloudflared
brew install cloudflared
```

### 1. Clone and install

```bash
git clone <repo-url> ~/apple-reminders-remote-mcp
cd ~/apple-reminders-remote-mcp
uv sync --all-extras
```

### 2. Build the Swift bridge

```bash
cd swift-bridge && swift build -c release && cd ..
```

On first run, macOS will prompt for Reminders access — grant it. You can verify permissions with:

```bash
./scripts/check-permissions.sh
```

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

```bash
# Generate a strong random token
REMINDERS_API_TOKEN=$(openssl rand -hex 32)
HOST=127.0.0.1
PORT=8000
SWIFT_BRIDGE_PATH=./swift-bridge/.build/release/EventKitCLI
# Your Cloudflare Tunnel hostname (required — without it, requests get 421)
EXTERNAL_HOST=reminders.yourdomain.com
```

### 4. Test locally

```bash
# Start the server
uv run python -m server

# In another terminal, verify it responds
curl -H "Authorization: Bearer <your-token>" http://localhost:8000/mcp
```

### 5. Set up Cloudflare Tunnel

```bash
# Authenticate with Cloudflare
cloudflared tunnel login

# Create a named tunnel
cloudflared tunnel create apple-reminders

# Create DNS record pointing to the tunnel
cloudflared tunnel route dns apple-reminders reminders.yourdomain.com
```

Create `tunnel/config.yml` (from the example):

```yaml
tunnel: <TUNNEL_UUID>
credentials-file: ~/.cloudflared/<TUNNEL_UUID>.json
ingress:
  - hostname: reminders.yourdomain.com
    service: http://localhost:8000
  - service: http_status:404
```

Test the tunnel:

```bash
cloudflared tunnel --config tunnel/config.yml run apple-reminders
```

### 6. Install as launch agents (auto-start on boot)

```bash
./scripts/install-service.sh
```

This installs two macOS launch agents:

- **MCP Server** — `~/Library/LaunchAgents/com.reminders-mcp.server.plist`
- **Cloudflare Tunnel** — `~/Library/LaunchAgents/com.reminders-mcp.tunnel.plist`

Both start automatically on login with `KeepAlive` enabled. Logs go to `~/Library/Logs/reminders-mcp-*.log`.

**Important:** Enable auto-login in System Settings so EventKit works when the Mac is running headless.

## Windows / Remote Client Setup

### Claude Code (CLI)

Native HTTP transport support — no proxy needed:

```bash
claude mcp add --transport http apple-reminders https://reminders.yourdomain.com/mcp \
  --header "Authorization: Bearer <your-token>" \
  --scope user
```

Or add to `.mcp.json` in your home directory or project root:

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

### Claude Desktop

Claude Desktop only supports stdio transport, so use
[mcp-remote](https://www.npmjs.com/package/mcp-remote) as a proxy.
Requires Node.js installed.

Add to `claude_desktop_config.json`
(`%APPDATA%\Claude\claude_desktop_config.json` on Windows,
`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "apple-reminders": {
      "command": "cmd",
      "args": [
        "/C",
        "npx",
        "-y",
        "mcp-remote",
        "https://reminders.yourdomain.com/mcp",
        "--header",
        "Authorization: Bearer <your-token>"
      ]
    }
  }
}
```

On macOS / Linux, use `npx` directly instead of `cmd /C npx`:

```json
{
  "mcpServers": {
    "apple-reminders": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "https://reminders.yourdomain.com/mcp",
        "--header",
        "Authorization: Bearer <your-token>"
      ]
    }
  }
}
```

## Development

```bash
# Install all dependencies (including dev)
uv sync --all-extras

# Run server (dev mode)
uv run python -m server

# Run server with auto-reload
uv run python -m server --reload

# Run tests
uv run pytest -v

# Lint and format
uv run ruff check .
uv run ruff format .

# Type check
uv run python -m mypy server/

# Full check
uv run ruff check . && uv run ruff format --check . && uv run python -m mypy server/
```

## MCP Tools

The server exposes 3 tools:

| Tool | Actions | Description |
|------|---------|-------------|
| `reminders_lists` | read, create, update, delete | Manage reminder lists |
| `reminders_tasks` | read, create, update, delete | CRUD for reminders with filters (list, priority, due date, tags, search) |
| `reminders_subtasks` | read, create, update, delete, toggle, reorder | Manage subtasks within a reminder |

## Security

- Server binds to `127.0.0.1` only — no direct port exposure
- Bearer token auth on all `/mcp` routes (timing-safe comparison)
- External access exclusively through Cloudflare Tunnel (encrypted, outbound-only)
- Token stored in `.env`, never committed
- Consider enabling [Cloudflare Access](https://developers.cloudflare.com/cloudflare-one/applications/) for an additional zero-trust auth layer
