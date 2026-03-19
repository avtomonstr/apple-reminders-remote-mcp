"""Tests for bearer token authentication middleware."""

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
