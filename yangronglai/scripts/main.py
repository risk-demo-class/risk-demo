"""Direct Uvicorn entry point for development and containers."""

import uvicorn

from app.config import settings


def main() -> None:
    uvicorn.run(
        "app.api:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=settings.APP_RELOAD,
    )


if __name__ == "__main__":
    main()

