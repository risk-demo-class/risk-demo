"""
电信风控系统 - 规则表 + 审计表建表 + 灌 12 条预置规则
用法:
  python scripts/init_rules.py          # 建表 + 灌规则 (会先 DROP)
  python scripts/init_rules.py --yes    # 跳过确认

跑这个脚本会建 7 张风控表:
  规则表: telecom_risk_rule (灌 12 条预置规则)
  审计表: telecom_risk_event / telecom_risk_feature / telecom_risk_assessment
          telecom_risk_case / telecom_risk_blacklist / telecom_card_profile
"""
import os
import sys

import pymysql

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "123321")
DB_NAME = os.getenv("DB_NAME", "telecom")

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SQL_RULES = os.path.join(_PROJECT_ROOT, "sql", "init_risk_tables.sql")
SQL_AUDIT = os.path.join(_PROJECT_ROOT, "sql", "init_risk_audit_tables.sql")


def _split_statements(sql_text: str) -> list[str]:
    statements = []
    for raw in sql_text.split(";\n"):
        lines = [ln for ln in raw.splitlines() if not ln.strip().startswith("--")]
        stmt = "\n".join(lines).strip()
        if stmt:
            statements.append(stmt)
    return statements


def _run_sql_file(cur, sql_file: str) -> int:
    """读 SQL 文件 + 逐条执行, 返回执行条数."""
    with open(sql_file, "r", encoding="utf-8") as f:
        sql_text = f.read()
    statements = _split_statements(sql_text)
    executed = 0
    for stmt in statements:
        head = stmt.lstrip().upper()
        if head.startswith("SELECT"):
            continue
        try:
            cur.execute(stmt); executed += 1
        except Exception as e:
            print(f"[WARN] 语句失败: {e}\n  {stmt[:80]}...")
    return executed


def main(yes: bool = False) -> None:
    print("=" * 60)
    print("电信风控 - 规则表 + 审计表建表 + 灌 12 条规则")
    print(f"  MySQL: {DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}")
    print("=" * 60)
    if not yes:
        try:
            input("即将 DROP + CREATE 7 张风控表并灌 12 条规则, 回车继续...")
        except (EOFError, KeyboardInterrupt):
            print("\n已取消"); sys.exit(0)

    conn = pymysql.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD,
        database=DB_NAME, charset="utf8mb4", autocommit=True,
    )

    with conn.cursor() as cur:
        # 1. 规则表 + 12 条预置规则
        print("[1/3] 建规则表 + 灌 12 条规则...")
        n1 = _run_sql_file(cur, SQL_RULES)
        # 2. 审计表 (6 张)
        print("[2/3] 建 6 张审计表 (event/feature/assessment/case/blacklist/profile)...")
        n2 = _run_sql_file(cur, SQL_AUDIT)
        # 3. 校验: 列出规则
        cur.execute(
            "SELECT rule_id, rule_name, risk_level, risk_score, action, priority "
            "FROM telecom_risk_rule ORDER BY priority DESC, rule_id"
        )
        rules = cur.fetchall()
        cur.execute(
            "SELECT risk_level, COUNT(*) FROM telecom_risk_rule GROUP BY risk_level"
        )
        level_stats = cur.fetchall()
        # 列出所有风控表
        cur.execute(
            "SELECT TABLE_NAME FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA='telecom' AND (TABLE_NAME LIKE 'telecom_risk_%' "
            "OR TABLE_NAME='telecom_card_profile') ORDER BY TABLE_NAME"
        )
        tables = [r[0] for r in cur.fetchall()]
    conn.close()

    print(f"\n[3/3] 执行完成 (规则 {n1} 条 + 审计 {n2} 条 SQL)")
    print(f"  风控表 ({len(tables)} 张): {', '.join(tables)}")
    print(f"\n  共 {len(rules)} 条规则:")
    print(f"  {'rule_id':<8}{'rule_name':<22}{'level':<6}{'score':<7}{'action':<12}{'prio'}")
    for rid, name, level, score, action, prio in rules:
        print(f"  {rid:<8}{name:<22}{level:<6}{score:<7}{action:<12}{prio}")
    print(f"\n  风险等级分布: {dict(level_stats)}")
    print("=" * 60)
    print("[OK] 风控表初始化完成. 下一步: python scripts/train_xgb_model.py")


if __name__ == "__main__":
    _yes = "--yes" in sys.argv or "-y" in sys.argv
    main(yes=_yes)
