"""Tests for Swift bridge models and communication."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from server.bridge.models import (
    BridgeRequest,
    BridgeResponse,
    Reminder,
    ReminderList,
    Subtask,
)
from server.bridge.swift_bridge import BridgeError, SwiftBridge


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
        """Test the send_command + _read_responses flow with a mock subprocess."""
        bridge = SwiftBridge(binary_path="/fake")

        # Set up mock process
        mock_process = MagicMock()
        mock_process.returncode = None

        # Mock stdin
        written_lines: list[bytes] = []
        mock_process.stdin = MagicMock()
        mock_process.stdin.write = lambda data: written_lines.append(data)
        mock_process.stdin.drain = AsyncMock()

        # Mock stdout -- we'll feed it a response after send_command writes
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
            sent = json.loads(written_lines[0])
            # Feed matching response to stdout
            resp = {
                "id": sent["id"],
                "success": True,
                "data": [{"id": "l1", "title": "Shopping"}],
            }
            await response_queue.put(json.dumps(resp).encode() + b"\n")
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
        req1 = json.loads(written_lines[0])
        req2 = json.loads(written_lines[1])

        # Respond in REVERSE order
        resp2 = {"id": req2["id"], "success": True, "data": "reminders"}
        resp1 = {"id": req1["id"], "success": True, "data": "lists"}
        await response_queue.put(json.dumps(resp2).encode() + b"\n")
        await response_queue.put(json.dumps(resp1).encode() + b"\n")

        result1 = await task1
        result2 = await task2

        assert result1.data == "lists"
        assert result2.data == "reminders"

        bridge._reader_task.cancel()
