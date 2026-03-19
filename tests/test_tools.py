"""Tests for MCP tool handlers with mocked Swift bridge."""

from __future__ import annotations

from unittest.mock import AsyncMock

from server.tools.reminders_lists import handle_reminders_lists
from server.tools.reminders_subtasks import handle_reminders_subtasks
from server.tools.reminders_tasks import handle_reminders_tasks
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
        result = await handle_reminders_lists(mock_bridge, action="update", id="l1")
        assert "error" in result.lower() or "required" in result.lower()

    async def test_delete_list(self, mock_bridge: AsyncMock) -> None:
        mock_bridge.send_command.return_value = make_success_response(None)
        result = await handle_reminders_lists(mock_bridge, action="delete", id="l1")
        mock_bridge.send_command.assert_awaited_once_with("delete_list", {"id": "l1"})
        assert "deleted" in result.lower() or "success" in result.lower()

    async def test_delete_list_missing_id(self, mock_bridge: AsyncMock) -> None:
        result = await handle_reminders_lists(mock_bridge, action="delete")
        assert "error" in result.lower() or "required" in result.lower()

    async def test_bridge_error_propagates(self, mock_bridge: AsyncMock) -> None:
        mock_bridge.send_command.return_value = make_error_response("Permission denied")
        result = await handle_reminders_lists(mock_bridge, action="read")
        assert "Permission denied" in result


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
        await handle_reminders_tasks(
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
        mock_bridge.send_command.assert_awaited_once_with("get_reminder", {"id": "r1"})
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
        await handle_reminders_tasks(
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
        result = await handle_reminders_tasks(mock_bridge, action="update", title="New")
        assert "error" in result.lower() or "required" in result.lower()

    async def test_delete_reminder(self, mock_bridge: AsyncMock) -> None:
        mock_bridge.send_command.return_value = make_success_response(None)
        result = await handle_reminders_tasks(mock_bridge, action="delete", id="r1")
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
        await handle_reminders_subtasks(
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
        await handle_reminders_subtasks(
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
        await handle_reminders_subtasks(
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
        await handle_reminders_subtasks(
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
        await handle_reminders_subtasks(
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
