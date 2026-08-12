"""P4 非破坏性迁移：新增用户表并扩展审计枚举。"""
import asyncio
import sys
from pathlib import Path

from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import settings  # noqa: E402
from app.database import AsyncSessionLocal, Base, async_engine  # noqa: E402
import app.models  # noqa: F401,E402
from app.service.auth import ensure_default_admin  # noqa: E402


ACTION_TYPES = (
    "CREATE_RULE", "UPDATE_RULE", "TOGGLE_RULE", "DELETE_RULE",
    "REVIEW_CASE", "AUTO_REJECT_CASE", "AUTO_CLOSE_CASE",
    "ADD_BLACKLIST", "REMOVE_BLACKLIST", "ASSIGN_CASE", "REOPEN_CASE",
    "CREATE_USER", "UPDATE_USER", "RESET_PASSWORD", "CHANGE_PASSWORD", "LOGIN", "LOGOUT",
)


async def main() -> None:
    if settings.DB_NAME.lower() == "ecs":
        raise RuntimeError("安全拒绝：P4 迁移不得作用于参考项目 ecs 数据库")
    action_enum = ",".join(f"'{value}'" for value in ACTION_TYPES)
    async with async_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        session_version_exists = (await connection.execute(text(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_schema = :schema AND table_name = 'app_user' "
            "AND column_name = 'session_version'"
        ), {"schema": settings.DB_NAME})).scalar_one()
        if not session_version_exists:
            await connection.execute(text(
                "ALTER TABLE app_user ADD COLUMN session_version INT NOT NULL DEFAULT 1 "
                "COMMENT '会话撤销版本' AFTER is_superuser"
            ))
        await connection.execute(text(
            f"ALTER TABLE risk_action_log MODIFY COLUMN action_type ENUM({action_enum}) NOT NULL COMMENT '操作类型'"
        ))
        await connection.execute(text(
            "ALTER TABLE risk_action_log MODIFY COLUMN target_type "
            "ENUM('rule','case','blacklist','user') NOT NULL COMMENT '对象类型'"
        ))
    async with AsyncSessionLocal() as db:
        admin = await ensure_default_admin(db)
    await async_engine.dispose()
    print(f"P4 迁移完成：18 张表；默认超级用户 {admin.username} 已就绪。")


if __name__ == "__main__":
    asyncio.run(main())
