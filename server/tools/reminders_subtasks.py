"""MCP tool for managing reminder subtasks."""

from __future__ import annotations

import json
from typing import Literal

from server.bridge.models import Subtask
from server.bridge.swift_bridge import SwiftBridge
from server.mcp_instance import get_bridge, mcp


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
            items: list[object] = resp.data if resp.data is not None else []
            subtasks = [Subtask.model_validate(item) for item in items]
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
            return json.dumps({"status": "deleted", "id": id}, ensure_ascii=False)

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
