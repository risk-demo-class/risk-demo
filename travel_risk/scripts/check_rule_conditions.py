"""检查指定规则的条件在 DB 和 API 中是否都存在"""
import json

import httpx
import pymysql


def main():
    targets = ["R027", "R030"]
    # 1. DB 直查
    conn = pymysql.connect(
        host="localhost", port=3307, user="root", password="123321",
        database="travel_risk", charset="utf8mb4",
    )
    cur = conn.cursor()
    cur.execute(
        "SELECT rule_id, rule_name, rule_condition, is_enabled, deleted_at "
        "FROM risk_rule WHERE rule_id IN (%s, %s)",
        targets,
    )
    db_rows = {r[0]: r for r in cur.fetchall()}
    conn.close()

    # 2. API 查询
    api_rows = {}
    for rid in targets:
        r = httpx.get(f"http://127.0.0.1:8000/api/rules/{rid}", timeout=10)
        api_rows[rid] = (r.status_code, r.json() if r.status_code == 200 else None)

    for rid in targets:
        print(f"===== {rid} =====")
        if rid in db_rows:
            r = db_rows[rid]
            print(f"[DB] {r[1]} | 条件: {r[2]} | enabled={r[3]} | deleted_at={r[4]}")
        else:
            print("[DB] 不存在!")
        status, body = api_rows[rid]
        print(f"[API] HTTP {status} | 条件: {body.get('rule_condition') if body else None}")


if __name__ == "__main__":
    main()
