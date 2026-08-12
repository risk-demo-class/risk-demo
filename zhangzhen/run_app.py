"""兼容 PyCharm 直接运行的应用入口。"""

from app.api import app


if __name__ == "__main__":
    import uvicorn

    from app.config import settings

    uvicorn.run(app, host=settings.HOST, port=settings.PORT)

