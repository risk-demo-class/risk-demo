"""
回归测试 (医疗版): force 模式 3 个 picker 的 source_id 必须用原始业务单 ID

电商版曾踩坑: _pick_forced_logistics_complaint 拼 source_id=f"COMP_{rec_id}",
导致 validator 强转 int 失败。医疗版 force picker 统一用原始 ID (source_id=sid)。
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = ROOT / "scripts" / "gen_risk_data_with_dates.py"


class TestForcePickerSourceId:
    """force 模式 3 个 picker 的 source_id 必须跟 validator 校验对得上"""

    def test_force_pickers_use_raw_id_no_prefix(self):
        """force picker 必须用原始业务单 ID, 不能拼前缀."""
        src = SCRIPT_PATH.read_text(encoding="utf-8")
        assert 'source_id=f"' not in src, (
            "force picker 不能再拼前缀字符串, 必须用原始业务单 ID"
        )
        assert "source_id=sid" in src, (
            "force picker 应直接用原始业务单 ID, 写 source_id=sid"
        )

    def test_all_three_force_pickers_in_script(self):
        """3 个 force picker 都应在脚本中定义 (医疗版: 处方/医保结算/药品订单)."""
        src = SCRIPT_PATH.read_text(encoding="utf-8")
        assert '"处方审核", _pick_forced_rx' in src, "应有处方 picker"
        assert '"医保结算", _pick_forced_claim' in src, "应有医保结算 picker"
        assert '"药品代购", _pick_forced_drug' in src, "应有药品订单 picker"
        assert src.count("RiskCheckRequest(") >= 3, "3 个 picker 都应构造 RiskCheckRequest"