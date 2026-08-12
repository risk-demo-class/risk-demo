"""验证规则管理前后端: API 条件字段 + 页面表头"""
import httpx


def main():
    # 1. API 列表: 30 条启用规则且每条带 rule_condition
    r = httpx.get("http://127.0.0.1:8000/api/rules", params={"page": 1, "page_size": 50}, timeout=10)
    assert r.status_code == 200, f"规则列表 API: {r.status_code}"
    data = r.json()
    print(f"规则总数: {data['total']}")
    assert data["total"] == 30, "应有 30 条启用规则"
    no_cond = [it["rule_id"] for it in data["items"] if not it.get("rule_condition")]
    assert not no_cond, f"以下规则缺少条件: {no_cond}"
    print(f"30 条规则全部带条件, 示例: R002 -> {data['items'][0]['rule_condition']}")

    # 2. 页面源码: 应包含"规则条件"表头
    p = httpx.get("http://127.0.0.1:8000/rules", timeout=10)
    assert p.status_code == 200, f"规则页面: {p.status_code}"
    assert "规则条件" in p.text, "页面缺少'规则条件'表头"
    print("页面包含 '规则条件' 表头 ✔")
    # 3. 页面 JS 里应有条件渲染函数
    assert "ruleConditionHtml" in p.text, "页面缺少条件渲染函数"
    print("页面包含条件渲染函数 ruleConditionHtml ✔")

    print("\n前后端规则条件链路验证通过 ✔")


if __name__ == "__main__":
    main()
