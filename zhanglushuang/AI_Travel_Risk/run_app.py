"""
项目根目录启动入口: python run_app.py
"""

import uvicorn

from app.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "scripts.main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=False,
    )
