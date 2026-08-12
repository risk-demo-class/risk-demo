"""
阶段3 回归测试: 物流版 _EVENT_SOURCE_VALIDATORS 的 source_id 校验规则一致性

背景 (旧电商版 bug): 物流投诉 picker 拼 source_id=f"COMP_{rec_id}", 但 validator 强转
int("COMP_xxx") 抛 ValueError, 每天固定 ~20 次失败.
物流版修复: 4 类物流事件的 source_id 都是业务表字符串主键 (parcel_id/decl_id/cod_id),
校验器只做字符串存在性检查, 不设 int caster → 不存在"拼前缀再强转"这类 bug.

阶段5 重写 gen_risk_data_with_dates.py 时, picker 只要保证 source_id 对应
_validators 里的 (model, field), 就能通过校验.
"""
import inspect

from sqlalchemy import String

from app.service import validator as validator_module


class TestForcePickerSourceId:
    """force 模式 picker 的 source_id 必须跟 validator 校验规则对得上 (物流版)"""

    def test_no_int_caster_in_validators(self):
        """物流 4 类事件的 source_id 都是字符串主键, 不应设 int caster (旧 bug 根因)."""
        for evt_types, (model, field, caster, _label, _status) in validator_module._EVENT_SOURCE_VALIDATORS.items():
            if model is None:
                continue  # 电商旧事件兼容: 无表, 跳过
            assert caster is None, (
                f"event_type={evt_types} 的 source_id 是字符串主键 {model.__name__}.{field}, "
                f"不该设 int caster (旧版 int('COMP_123') ValueError 的根因)"
            )

    def test_field_is_primary_key_of_model(self):
        """每个物流事件的校验字段必须是对应业务表的字符串主键 (PK)."""
        # 业务表主键 (与 app/models_business.py 定义一致)
        expected_pk = {
            "Parcel": "parcel_id",
            "DangerousDeclaration": "decl_id",
            "CodTransaction": "cod_id",
        }
        for evt_types, (model, field, _caster, _label, _status) in validator_module._EVENT_SOURCE_VALIDATORS.items():
            if model is None:
                continue
            assert field == expected_pk[model.__name__], (
                f"event_type={evt_types} 应校验 {model.__name__}.{expected_pk[model.__name__]}, "
                f"实际配了 {field}"
            )
            # 主键是字符串类型 → source_id 直接用字符串拼即可, 无需前缀
            pk_col = getattr(model, field)
            assert isinstance(pk_col.type, String), (
                f"{model.__name__}.{field} 应是字符串主键, 实际类型: {pk_col.type}"
            )

    def test_each_event_maps_to_expected_model(self):
        """4 类物流事件 → 4 个正确模型 (事件↔来源表 一一对应)."""
        mapping = {
            "parcel_pickup": "Parcel",
            "cross_border_ship": "Parcel",
            "dangerous_declare": "DangerousDeclaration",
            "cod_settlement": "CodTransaction",
        }
        table = {evt: model.__name__ if model else None
                 for evt_types, (model, _f, _c, _l, _s) in validator_module._EVENT_SOURCE_VALIDATORS.items()
                 for evt in evt_types}
        for evt, expected_model in mapping.items():
            assert table.get(evt) == expected_model, (
                f"{evt} 应映射到 {expected_model}, 实际 {table.get(evt)}"
            )

    def test_source_id_can_be_plain_string_no_prefix(self):
        """source_id 直接用业务主键字符串 (如 P000001), 不带任何前缀 → 能通过校验."""
        # 静态断言: validator 对 logistics 事件只做存在性检查, 不拼前缀 (verify 在 ensure_exists)
        src = inspect.getsource(validator_module)
        assert "f\"COMP_" not in src, "不应再有 COMP_ 前缀拼接逻辑"
        # 4 个 logistics 事件都列在派发表里, 校验走 ensure_exists (字符串精确匹配)
        logistics_events = ["parcel_pickup", "dangerous_declare", "cross_border_ship", "cod_settlement"]
        for evt in logistics_events:
            assert any(evt in evt_types for evt_types, *_ in validator_module._EVENT_SOURCE_VALIDATORS.items()), (
                f"{evt} 必须配置在 _EVENT_SOURCE_VALIDATORS 里"
            )
