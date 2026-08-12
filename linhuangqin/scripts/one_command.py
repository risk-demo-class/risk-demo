"""物流风控系统 - 一键部署脚本
Usage:
    python scripts/one_command.py [--reset] [--count N]
"""
import argparse
import sys
from pathlib import Path

# 确保项目根在 sys.path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from scripts.init_db import init_db
from scripts.gen_logistics_data import main as gen_data
from scripts.gen_risky_users import main as gen_risky
from scripts.train_xgb_model import main as train_model


def main():
    parser = argparse.ArgumentParser(description="物流风控系统 - 一键部署")
    parser.add_argument("--reset", action="store_true", help="重置: 删除表后重建")
    parser.add_argument("--count", type=int, default=200, help="业务数据生成条数")
    parser.add_argument("--risky", type=int, default=30, help="高风险用户生成条数")
    parser.add_argument("--no-train", action="store_true", help="跳过模型训练")
    args = parser.parse_args()

    print("=" * 60)
    print("物流风控系统 - 一键部署")
    print("=" * 60)

    # Step 1: 初始化数据库
    print("\n[1/4] 初始化数据库...")
    init_db(reset=args.reset)
    print("  ✓ 数据库初始化完成")

    # Step 2: 生成业务数据
    print("\n[2/4] 生成物流业务数据...")
    gen_data(count=args.count, reset=False)
    gen_risky(count=args.risky)
    print(f"  ✓ 已生成 {args.count} 条物流事件 + {args.risky} 个高风险用户")

    # Step 3: 训练模型
    if not args.no_train:
        print("\n[3/4] 训练 XGBoost 模型...")
        train_model(limit=1000)
        print("  ✓ 模型训练完成")
    else:
        print("\n[3/4] 跳过模型训练 (--no-train)")

    # Step 4: 验证
    print("\n[4/4] 验证...")
    from sqlalchemy import text
    from app.database import async_engine
    import asyncio

    async def verify():
        async with async_engine.connect() as conn:
            tables = await conn.execute(text("SHOW TABLES"))
            events = await conn.execute(text("SELECT COUNT(*) FROM logistics_event_log"))
            shippers = await conn.execute(text("SELECT COUNT(*) FROM shipper_info"))
            waybills = await conn.execute(text("SELECT COUNT(*) FROM waybill_info"))
            print(f"  ✓ 数据库表: {tables.rowcount} 张")
            print(f"  ✓ 物流事件: {events.scalar()} 条")
            print(f"  ✓ 卖家账户: {shippers.scalar()} 个")
            print(f"  ✓ 运单数据: {waybills.scalar()} 条")

    asyncio.run(verify())

    print("\n" + "=" * 60)
    print("部署完成!")
    print(f"  启动服务: python scripts/main.py")
    print(f"  API 文档: http://localhost:8000/docs")
    print("=" * 60)


if __name__ == "__main__":
    main()
