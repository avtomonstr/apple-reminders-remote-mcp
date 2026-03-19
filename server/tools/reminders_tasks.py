"""MCP tool for managing reminder tasks."""

from __future__ import annotations

import json
from typing import Literal

from server.bridge.models import Reminder
from server.bridge.swift_bridge import SwiftBridge
from server.mcp_instance import get_bridge, mcp


async def handle_reminders_tasks(
    bridge: SwiftBridge,
    *,
    action: Literal["read", "create", "update", "delete"],
    id: str | None = None,
    title: str | None = None,
    filter_list: str | None = None,
    show_completed: bool = False,
    search: str | None = None,
    due_within: Literal["today", "tomorrow", "this-week", "overdue", "no-date"]
    | None = None,
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
                return json.dumps(reminder.model_dump(), indent=2, ensure_ascii=False)

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
            items: list[object] = resp.data if resp.data is not None else []
            reminders = [Reminder.model_validate(item) for item in items]
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
            return json.dumps(created.model_dump(), indent=2, ensure_ascii=False)

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
            return json.dumps(updated.model_dump(), indent=2, ensure_ascii=False)

        case "delete":
            if not id:
                return "Error: 'id' is required for delete action."
            resp = await bridge.send_command("delete_reminder", {"id": id})
            if not resp.success:
                return f"Error: {resp.error}"
            return json.dumps({"status": "deleted", "id": id}, ensure_ascii=False)


@mcp.tool()
async def reminders_tasks(
    action: Literal["read", "create", "update", "delete"],
    id: str | None = None,
    title: str | None = None,
    filter_list: str | None = None,
    show_completed: bool = False,
    search: str | None = None,
    due_within: Literal["today", "tomorrow", "this-week", "overdue", "no-date"]
    | None = None,
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
    - read: List reminders (filters: filter_list, show_completed,
      search, due_within, filter_priority, filter_tags) or get by id
    - create: Create a reminder (requires: title; optional:
      target_list, due_date, note, url, priority, tags, subtasks,
      recurrence, location_trigger, alarms)
    - update: Update a reminder (requires: id; optional: any field)
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
