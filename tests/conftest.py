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
