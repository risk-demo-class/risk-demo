"""验证 AI 助手: 默认按钮问题 + LLM 接入状态"""
import httpx


def main():
    # 1. 健康状态
    h = httpx.get("http://localhost:8000/api/agent/health", timeout=10).json()
    print(f"LLM 接入: {h['enabled']} | 模型: {h['model']}")
    assert h["enabled"], "LLM 应已配置"

    # 2. 页面包含默认按钮模块
    page = httpx.get("http://localhost:8000/chat", timeout=10).text
    assert "快速提问" in page and "quickAsk" in page and "agent-status" in page
    print("页面包含默认按钮模块与状态徽章 ✔")

    # 3. 默认按钮问题走 LLM 并返回有效回答
    for q in ["有哪些风险规则", "查看决策分布", "列出 28 维特征", "解释 R002 一票否决规则"]:
        r = httpx.post(
            "http://localhost:8000/api/agent/chat",
            json={"message": q, "session_id": "verify-final"},
            timeout=70,
        ).json()
        print(f"Q: {q}")
        print(f"  mode={r.get('mode')} | reply: {r.get('reply', '')[:120].replace(chr(10), ' / ')}")
        assert r.get("mode") == "llm", f"{q} 应走 LLM"
        assert r.get("reply"), f"{q} 应有回复"

    print("\nAI 助手验证通过: LLM 已接入 + 默认按钮可用 ✔")


if __name__ == "__main__":
    main()
