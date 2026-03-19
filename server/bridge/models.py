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
