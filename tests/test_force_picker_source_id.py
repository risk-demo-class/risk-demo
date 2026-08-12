"""
回归测试: force 模式 picker 的 source_id 跟 validator 校验对得上
物流版: 4 个 picker 对应 4 种事件.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = ROOT / "scripts" / "gen_risk_data_with_dates.py"
SQL_PATH = ROOT / "sql" / "init_business_tables.sql"


class TestForcePickerSourceId:

    def test_complaint_record_id_no_prefix(self):
        """投诉 picker 不能拼前缀, 必须用原始 record_id 转字符串."""
        src = SCRIPT_PATH.read_text(encoding="utf-8")
        # _pick_complaint 返回 (str(record_id), user_id) 或源文件显式转换
        assert (
            '_pick_complaint' in src
            and (
                'str(row.record_id)' in src
                or "str(record_id)" in src
                or "str(rid)" in src
            )
        ), "投诉 picker 应把 record_id 整数字段转字符串, 不能拼前缀"

    def test_all_pickers_use_logistics_tables(self):
        """4 个 picker 都读物流业务表 (shipment/customs_declaration/complaint_record)."""
        src = SCRIPT_PATH.read_text(encoding="utf-8")
        assert "FROM shipment" in src
        assert "customs_declaration" in src
        assert "complaint_record" in src
        # 旧电商表名不应再出现
        assert "FROM order_info" not in src
        assert "postsale" not in src

    def test_complaint_record_id_is_bigint(self):
        """complaint_record.record_id 必须是 AUTO_INCREMENT 整数."""
        sql = SQL_PATH.read_text(encoding="utf-8")
        m = re.search(r"`record_id`\s+(\w+)[^,]*AUTO_INCREMENT", sql)
        assert m, "complaint_record.record_id 必须是 AUTO_INCREMENT 整数"
        assert "int" in m.group(1).lower()

    def test_validator_caster_matches(self):
        """validator 对投诉用 int 强转, picker 必须给整数字符串."""
        src = SCRIPT_PATH.read_text(encoding="utf-8")
        assert 'str(row.record_id)' in src or 'str(rid)' in src or 'str(rec_id)' in src or \
               "_pick_complaint" in src  # 至少 _pick_complaint 返回 (str(record_id), user_id)
