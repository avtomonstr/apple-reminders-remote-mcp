"""MCP tool for managing reminder lists."""

from __future__ import annotations

import json
from typing import Literal

from server.bridge.models import ReminderList
from server.bridge.swift_bridge import SwiftBridge
from server.mcp_instance import get_bridge, mcp


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
            items: list[object] = resp.data if resp.data is not None else []
            lists = [ReminderList.model_validate(item) for item in items]
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
