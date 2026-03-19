"""Entry point: python -m server."""

from __future__ import annotations

import os

import uvicorn
from dotenv import load_dotenv

load_dotenv()


def main() -> None:
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))

    uvicorn.run(
        "server.app:create_asgi_app",
        host=host,
        port=port,
        factory=True,
        log_level="info",
    )


if __name__ == "__main__":
    main()
