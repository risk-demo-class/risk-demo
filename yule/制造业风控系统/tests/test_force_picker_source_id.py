"""
制造业回归测试: gen_risk_data_with_dates.py 的 picker 用原始业务 ID 当 source_id,
跟 validator 的事件派发表对得上 (不带前缀拼接, 避免 ID 对不上).
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = ROOT / "scripts" / "gen_risk_data_with_dates.py"
VALIDATOR_PATH = ROOT / "app" / "service" / "validator.py"


class TestManufacturingPickerSourceId:
    """picker 的 source_id 必须跟 validator 校验对得上"""

    def test_source_ids_are_raw_ids(self):
        """picker 不能用 f\"XXX_\" 前缀拼 source_id, 必须用 DB 原始 ID."""
        src = SCRIPT_PATH.read_text(encoding="utf-8")
        assert 'source_id=f"' not in src, (
            "picker 不能拼前缀字符串当 source_id, 直接用 DB 里的 order_id/warranty_id/report_id"
        )
        assert "row.order_id" in src and "row.warranty_id" in src and "row.report_id" in src, (
            "3 个 picker 应返回 DB 原始 order_id/warranty_id/report_id"
        )

    def test_three_manufacturing_events_in_picker(self):
        """脚本应支持 3 种制造业事件: 经销商订货 / 设备保修 / 跨区串货举报."""
        src = SCRIPT_PATH.read_text(encoding="utf-8")
        assert '"经销商订货"' in src, "应有经销商订货事件"
        assert '"设备保修"' in src, "应有设备保修事件"
        assert '"跨区串货举报"' in src, "应有跨区串货举报事件"
        assert src.count("RiskCheckRequest(") >= 1, "应构造 RiskCheckRequest"

    def test_validator_dispatch_matches_picker_events(self):
        """validator 事件派发表应覆盖 3 种制造业事件."""
        src = VALIDATOR_PATH.read_text(encoding="utf-8")
        assert '"经销商订货"' in src, "validator 缺经销商订货派发"
        assert '"设备保修"' in src, "validator 缺设备保修派发"
        assert '"跨区串货举报"' in src, "validator 缺跨区串货举报派发"
