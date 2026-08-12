# -*- coding: utf-8 -*-
"""数据库初始化（宝典第 17 章 练习 1）

一条命令拉起整套教学环境：

    python scripts/init_db.py                # 建表 + 灌 30 条规则（幂等，不动已有数据）
    python scripts/init_db.py --with-business # 再造 60 个用户的业务数据
    python scripts/init_db.py --rebuild       # 删表重建 + 造数据（危险：清空一切）
    python scripts/init_db.py --users 120 --seed 7

三步做什么：
    ① `init_database()`  → 25 张表 DDL（17 业务 + 7 风控 + 1 审计）+ 30 条预置规则
    ② `business_seed`    → 17 张业务表填充 10 类人设，保证 30 条规则都有样本能命中
    ③ 校验报告           → 打印表行数、人设分布、可直接用于风控检查的高危样本单号
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app import models                                    # noqa: E402
from app.config import settings                           # noqa: E402
from app.data import business_seed                         # noqa: E402
from app.data.rules_seed import CATEGORY_STATS, LEVEL_STATS, PRESET_RULES, VETO_RULE_IDS  # noqa: E402
from app.database import init_database, pool, session_scope  # noqa: E402

BAR = "=" * 76


def _say(msg: str) -> None:
    print(f"  {msg}")


def _section(title: str) -> None:
    print(f"\n{BAR}\n  {title}\n{BAR}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="智学安·教育风控平台 数据库初始化（建表 + 30 条规则 + 业务样例数据）")
    p.add_argument("--with-business", action="store_true", help="同时生成业务样例数据")
    p.add_argument("--rebuild", action="store_true",
                   help="删表重建并生成业务数据（清空所有数据，含风控事件）")
    p.add_argument("--users", type=int, default=60, help="业务样例用户数（默认 60）")
    p.add_argument("--seed", type=int, default=42, help="随机种子（默认 42，保证可复现）")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    with_business = args.with_business or args.rebuild

    _section(f"{settings.APP_NAME} {settings.APP_VERSION} · 数据库初始化")
    _say(f"数据库文件 : {settings.DB_PATH}")
    _say(f"连接池     : pool_size={settings.DB_POOL_SIZE} max_overflow={settings.DB_MAX_OVERFLOW}")
    _say(f"模式       : {'删表重建（--rebuild）' if args.rebuild else '幂等初始化'}")

    # ---------------------------------------------------------- ① 建表 + 规则
    _section("步骤 1/3 · 建表 + 灌预置规则")
    stats = init_database(drop=args.rebuild)
    _say(f"表结构     : {stats['tables']} 张 "
         f"（业务 {models.TABLE_STATS['business']} + 风控 {models.TABLE_STATS['risk']} "
         f"+ 审计 {models.TABLE_STATS['audit']}）")
    _say(f"预置规则   : 本次新增 {stats['rules']} 条 / 规则库共 {len(PRESET_RULES)} 条")
    _say(f"规则分类   : " + " · ".join(f"{k} {v}" for k, v in CATEGORY_STATS.items()))
    _say(f"风险等级   : " + " · ".join(f"{k} {v}" for k, v in LEVEL_STATS.items()))
    _say(f"一票否决   : {', '.join(VETO_RULE_IDS)}（risk_level=极高 → final=max(final, "
         f"{settings.RISK_VETO_MIN_SCORE})）")

    # ---------------------------------------------------------- ② 业务数据
    result = None
    if with_business:
        _section(f"步骤 2/3 · 生成业务样例数据（users={args.users} seed={args.seed}）")
        with session_scope() as db:
            result = business_seed.generate(db, users=args.users, seed=args.seed,
                                            reset=True, progress=_say)
        _say(f"合计写入   : {result['total_rows']} 行 / {len(result['tables'])} 张表")
    else:
        _section("步骤 2/3 · 业务样例数据（跳过）")
        _say("未指定 --with-business：只建表灌规则。")
        _say("若要一键造数据：python scripts/init_db.py --with-business")

    # ---------------------------------------------------------- ③ 校验报告
    _section("步骤 3/3 · 校验报告")
    with session_scope() as db:
        rows = []
        for name in models.ALL_TABLES:
            cnt = db.scalar(f'SELECT COUNT(1) FROM "{name}"')
            rows.append((name, int(cnt), models.ALL_TABLES[name].group))
        width = max(len(r[0]) for r in rows)
        for group in ("业务", "风控", "审计"):
            print(f"\n  【{group}表】")
            for name, cnt, grp in rows:
                if grp != group:
                    continue
                flag = "" if cnt else "   ← 空"
                print(f"    {name.ljust(width)}  {str(cnt).rjust(6)} 行{flag}")

    if result:
        print(f"\n  【人设分布】")
        for label, cnt in sorted(result["persona_distribution"].items(),
                                 key=lambda kv: -kv[1]):
            print(f"    {label.ljust(26)} {cnt} 人")

        print("\n  【可直接用于风控检查的高危样本】")
        header = ("user_id".ljust(9) + "人设".ljust(24) + "行为数".rjust(6)
                  + "申诉率".rjust(9) + "退课率".rjust(9) + "均投入".rjust(11) + "  样例记录")
        print("    " + header)
        for s in result["highlights"]:
            refund = "{:.0%}".format(s["refund_rate"]).rjust(9)
            postsale = "{:.0%}".format(s["postsale_rate"]).rjust(9)
            avg = "{:.0f}".format(s["avg_amount"]).rjust(11)
            print("    " + s["user_id"].ljust(9) + s["persona_label"].ljust(24)
                  + str(s["orders"]).rjust(6) + refund + postsale + avg
                  + "  " + s["sample_order"])

        demo = next((s for s in result["highlights"] if s["persona"] == "combo_fraud"), None)
        if demo:
            _section("下一步：跑一次 7 步流水线（宝典第 17 章 练习 2）")
            payload = ('{"event_type":"考试","source_id":"%s","user_id":"%s","order_id":"%s"}'
                       % (demo["sample_order"], demo["user_id"], demo["sample_order"]))
            print("  1) 启动服务：  python scripts/main.py")
            print("  2) 一票否决样本（预期 极高 → 拒绝）：")
            print("     curl -X POST http://localhost:%d/api/risk/check \\" % settings.PORT)
            print("       -H \"Content-Type: application/json\" \\")
            print("       -d '%s'" % payload)
            print("  3) 或打开控制台「风控检查」页，点「载入高危样本」一键填充。")

    _section("完成")
    _say("控制台   http://127.0.0.1:%d/" % settings.PORT)
    _say("API 目录 http://127.0.0.1:%d/docs" % settings.PORT)
    if not with_business:
        _say("提示：还没有业务数据，风控检查会因「订单不存在」而 404。")
    print()
    return 0


if __name__ == "__main__":
    try:
        code = main()
    finally:
        pool.dispose()
    sys.exit(code)
