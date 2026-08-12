"""
【银行版】回归测试: gen_risk_data.py 4 个 picker 的 source_id 跟 validator 校验对得上

银行版场景: 转账/登录/贷款申请/信用卡 4 大事件.
4 个 picker (_pick_txn/_pick_login/_pick_loan/_pick_card) 的 source_id 直接取
原始业务 ID (txn_id/login_id/loan_id/card_id, 均为 VARCHAR(50), 无前缀拼装),
validator._EVENT_SOURCE_VALIDATORS 的 caster 全为 None (直接比较, 无 int 强转).
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = ROOT / "scripts" / "gen_risk_data.py"
SQL_PATH = ROOT / "sql" / "init_bank_tables.sql"


class TestBankPickersSourceId:
    """gen_risk_data.py 4 个 picker 的 source_id 必须跟 validator 校验对得上"""

    def test_pickers_use_raw_business_ids_no_prefix(self):
        """4 个 picker 的 source_id 必须用原始业务 ID, 不能拼前缀."""
        src = SCRIPT_PATH.read_text(encoding="utf-8")
        # 只看 _build_request 函数体 (source_id 的最终赋值处)
        body = src.split("def _build_request", 1)[1]
        assert 'source_id=picked["txn_id"]' in body, "转账 picker 应直接用 txn_id"
        assert 'source_id=picked["login_id"]' in body, "登录 picker 应直接用 login_id"
        assert 'source_id=picked["loan_id"]' in body, "贷款 picker 应直接用 loan_id"
        assert 'source_id=picked["card_id"]' in body, "信用卡 picker 应直接用 card_id"
        # 不允许在 _build_request 里拼前缀字符串 (回归保护)
        assert 'source_id=f"' not in body, "source_id 不得再拼前缀字符串"

    def test_all_four_pickers_in_script(self):
        """4 个 picker 都应在脚本中定义, 覆盖 4 大银行场景."""
        src = SCRIPT_PATH.read_text(encoding="utf-8")
        assert "async def _pick_txn" in src, "应有转账 picker"
        assert "async def _pick_login" in src, "应有登录 picker"
        assert "async def _pick_loan" in src, "应有贷款 picker"
        assert "async def _pick_card" in src, "应有信用卡 picker"

    def test_build_request_covers_four_event_types(self):
        """_build_request 必须覆盖 4 种事件类型的 RiskCheckRequest 构造."""
        src = SCRIPT_PATH.read_text(encoding="utf-8")
        for evt in ("转账", "登录", "贷款申请", "信用卡"):
            assert f'event_type == "{evt}"' in src or evt in src, (
                f"_build_request 应覆盖 {evt} 场景"
            )
        assert src.count("RiskCheckRequest(") >= 4, "4 个场景都应构造 RiskCheckRequest"

    def test_business_ids_are_varchar(self):
        """4 张业务表的 ID 都必须是 VARCHAR (跟 validator 直接比较对应, 无 int 强转)."""
        sql = SQL_PATH.read_text(encoding="utf-8")
        for col in ("txn_id", "login_id", "loan_id", "card_id"):
            assert f"`{col}` VARCHAR(50)" in sql, (
                f"业务表 {col} 必须是 VARCHAR(50), 与 validator 字符串比较对齐"
            )

    def test_validator_casters_all_none(self):
        """validator 映射的 caster 全为 None: source_id 不做 int 强转, 字符串直接比较."""
        src = SCRIPT_PATH.read_text(encoding="utf-8")
        from app.service.validator import _EVENT_SOURCE_VALIDATORS
        assert len(_EVENT_SOURCE_VALIDATORS) == 4, "银行版应有 4 个事件类型映射"
        for evt_types, (model, field, caster, label, status) in _EVENT_SOURCE_VALIDATORS.items():
            assert caster is None, (
                f"{evt_types} 的 caster 应为 None (VARCHAR 直接比较), 实际 {caster}"
            )
        # 脚本 source_id 与映射字段名一一对应
        assert 'picked["txn_id"]' in src and "txn_id" in str(_EVENT_SOURCE_VALIDATORS)
