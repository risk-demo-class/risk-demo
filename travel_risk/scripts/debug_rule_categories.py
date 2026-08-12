"""排查: 各分类规则在 DB 与 API 中的分布是否一致"""
import httpx
import pymysql


def main():
    # 1. DB 分布
    conn = pymysql.connect(
        host="localhost", port=3307, user="root", password="123321",
        database="travel_risk", charset="utf8mb4",
    )
    cur = conn.cursor()
    cur.execute(
        "SELECT rule_category, COUNT(*) FROM risk_rule "
        "WHERE deleted_at IS NULL GROUP BY rule_category ORDER BY rule_category"
    )
    db_dist = dict(cur.fetchall())
    cur.execute("SELECT rule_id, rule_category FROM risk_rule WHERE deleted_at IS NULL ORDER BY priority DESC")
    db_all = cur.fetchall()
    conn.close()
    print("[DB] 各分类规则数:", db_dist)
    print("[DB] 全部规则数:", len(db_all))

    # 2. API 无筛选
    r = httpx.get("http://127.0.0.1:8000/api/rules", params={"page": 1, "page_size": 100}, timeout=10)
    api_all = r.json()
    print(f"[API] 无筛选: HTTP {r.status_code}, total={api_all['total']}, 返回 {len(api_all['items'])} 条")

    # 3. API 各分类筛选
    categories = ["下单欺诈", "支付风险", "账户风险", "退改滥用", "出行人风险", "供应商风险", "综合风险"]
    for cat in categories:
        resp = httpx.get(
            "http://127.0.0.1:8000/api/rules",
            params={"page": 1, "page_size": 100, "category": cat},
            timeout=10,
        )
        body = resp.json()
        ids = [it["rule_id"] for it in body.get("items", [])]
        print(f"[API] category={cat}: HTTP {resp.status_code}, total={body.get('total')}, ids={ids}")


if __name__ == "__main__":
    main()
