"""Bearer token authentication middleware for MCP endpoints."""

from __future__ import annotations

import hmac

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class BearerAuthMiddleware(BaseHTTPMiddleware):
    """Validates Bearer token on /mcp routes.

    Non-MCP routes (e.g., /health) pass through without auth.
    """

    def __init__(self, app: object, token: str) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._token = token

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.url.path.startswith("/mcp"):
            auth_header = request.headers.get("authorization", "")
            if not auth_header.startswith("Bearer "):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)

            provided_token = auth_header.removeprefix("Bearer ")
            if not hmac.compare_digest(provided_token, self._token):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)

        return await call_next(request)
