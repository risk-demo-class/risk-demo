"""
制造业回归测试: 5 个事件 picker 的 source_id 跟 validator 校验对得上

关键约束:
  - 串货举报 source_id 是 report_id (bigint), validator 强转 int(), 必须用 str(report_id) 不带前缀
  - 保修/维修 source_id 是 warranty_id (varchar)
  - 订货/采购 source_id 是 order_id (varchar)
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PICKER_PATH = ROOT / "scripts" / "mfg_pickers.py"
SCRIPT_PATH = ROOT / "scripts" / "gen_risk_data_with_dates.py"
SQL_PATH = ROOT / "sql" / "init_business_tables.sql"


class TestPickerSourceId:
    """5 种事件 picker 的 source_id 必须跟 validator 校验对得上"""

    def test_report_source_id_no_prefix(self):
        """串货举报 picker 不能用前缀, 必须用原始 report_id (整数转字符串)."""
        src = PICKER_PATH.read_text(encoding="utf-8")
        assert 'str(row.report_id)' in src, (
            "串货举报 source_id 应直接用 report_id: str(row.report_id)"
        )

    def test_all_five_event_pickers_in_script(self):
        """5 种事件都应出现在 picker 里."""
        src = PICKER_PATH.read_text(encoding="utf-8")
        for et in ("经销商订货", "采购订单", "保修申请", "售后维修", "串货举报"):
            assert et in src, f"缺少事件类型 {et}"

    def test_report_id_is_bigint(self):
        """cross_region_report.report_id 必须是 AUTO_INCREMENT 整数."""
        sql = SQL_PATH.read_text(encoding="utf-8")
        m = re.search(r"`report_id`\s+(\w+)[^,]*AUTO_INCREMENT", sql)
        assert m, "cross_region_report.report_id 必须是 AUTO_INCREMENT 整数"
        col_type = m.group(1).lower()
        assert "int" in col_type or "bigint" in col_type, f"report_id 必须是整数, 实际: {col_type}"

    def test_gen_risk_data_with_dates_uses_pickers(self):
        """带日期造数脚本应复用 mfg_pickers, 不再出现旧电商 picker."""
        src = SCRIPT_PATH.read_text(encoding="utf-8")
        assert "pick_random_event" in src
        assert "postsale" not in src.lower(), "旧电商 postsale picker 不应残留"
        assert "物流投诉" not in src, "旧电商物流投诉 picker 不应残留"
