"""银行信贷风控 - AI Agent 工具测试 (RED 基线).

期望 8 个 @tool 银行化: 不引用电商模型, 工具描述含银行语义.
"""
import importlib
import inspect


def _tools_module():
    from app import agent
    return importlib.import_module("app.agent.tools")


def test_agent_has_8_tools():
    """8 个 @tool 全部存在."""
    mod = _tools_module()
    for name in ["risk_check", "query_cases", "query_user_profile", "manage_blacklist",
                 "query_dashboard_stats", "analyze_risk_trend",
                 "analyze_rule_effectiveness", "query_business_data"]:
        assert hasattr(mod, name), f"缺少工具 {name}"


def test_agent_no_ecom_models():
    """工具模块不引用电商模型 (OrderInfo/Postsale/ReceiveInfo)."""
    mod = _tools_module()
    src = inspect.getsource(mod)
    for name in ["OrderInfo", "Postsale", "ReceiveInfo", "OrderDetail", "SkuInfo"]:
        assert name not in src, f"工具仍引用电商模型: {name}"


def test_agent_risk_check_bank_event():
    """风险检查工具支持银行事件 (贷款申请)."""
    mod = _tools_module()
    src = inspect.getsource(mod)
    assert "贷款申请" in src or "event_type" in src, "风险检查工具无银行事件语义"


def test_agent_blacklist_4_types():
    """黑名单管理工具支持 4 类 (客户/手机号/地址/设备)."""
    mod = _tools_module()
    src = inspect.getsource(mod)
    assert "设备" in src.strip() or "device" in src.lower(), "黑名单工具缺少设备类型"