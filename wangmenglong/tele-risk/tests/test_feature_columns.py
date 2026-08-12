"""
特征列对齐测试 (无需 DB): 确保 feature.py 算出的特征 key 跟 ml_model.FEATURE_COLUMNS
一一对应, 防止训练/推理特征错位.

这是 tele-risk 最容易出错的点: 3 处定义特征顺序, 必须同步:
  1. app/engine/feature.py 的 compute_*_features (算特征)
  2. app/engine/ml_model.py 的 FEATURE_COLUMNS (训练 + 推理)
  3. scripts/train_xgb_model.py 的 _compute_features (训练取数)
"""
from app.engine.ml_model import FEATURE_COLUMNS


# feature.py 各 compute_*_features 返回的 key (硬编码, 跟代码对齐)
CARD_FEATURES = {"card_age_days", "card_is_iot", "card_intl_enabled",
                 "card_roam_type_code", "card_status_normal"}
CUST_FEATURES = {"cust_card_count", "cust_id_multi_card_flag",
                 "cust_face_verify_passed", "cust_risk_tag_high_flag",
                 "cust_open_channel_count"}
CDR_FEATURES = {"cdr_out_count_1h", "cdr_out_count_24h", "cdr_in_count_24h",
                "cdr_distinct_cell_1h", "cdr_short_call_ratio",
                "cdr_intl_incoming_24h", "cdr_night_call_ratio", "cdr_avg_duration_sec"}
DEV_FEATURES = {"dev_cards_on_imei", "dev_card_imei_mismatch_flag", "dev_binding_changes_30d"}
CHANNEL_FEATURES = {"channel_open_count_1h", "channel_is_agent_flag"}
IOT_FEATURES = {"iot_data_burst_ratio", "iot_card_device_unbound_flag"}

ALL_FEATURES = CARD_FEATURES | CUST_FEATURES | CDR_FEATURES | DEV_FEATURES | CHANNEL_FEATURES | IOT_FEATURES


class TestFeatureColumns:
    def test_total_25(self):
        """特征总数必须是 25 (5 族)."""
        assert len(FEATURE_COLUMNS) == 25

    def test_feature_keys_match(self):
        """feature.py 算出的 25 个 key 跟 FEATURE_COLUMNS 完全一致."""
        assert set(FEATURE_COLUMNS) == ALL_FEATURES

    def test_no_duplicates(self):
        """FEATURE_COLUMNS 无重复."""
        assert len(FEATURE_COLUMNS) == len(set(FEATURE_COLUMNS))

    def test_group_counts(self):
        """5 个特征族的数量: 号卡5 / 客户5 / 通信8 / 设备3 / 渠道2 / 物联网2."""
        assert len(CARD_FEATURES) == 5
        assert len(CUST_FEATURES) == 5
        assert len(CDR_FEATURES) == 8
        assert len(DEV_FEATURES) == 3
        assert len(CHANNEL_FEATURES) == 2
        assert len(IOT_FEATURES) == 2

    def test_feature_order_by_group(self):
        """FEATURE_COLUMNS 按特征族分组排列 (号卡→客户→通信→设备→渠道→物联网)."""
        groups = [
            CARD_FEATURES, CUST_FEATURES, CDR_FEATURES,
            DEV_FEATURES, CHANNEL_FEATURES, IOT_FEATURES,
        ]
        idx = 0
        for group in groups:
            for _ in group:
                assert FEATURE_COLUMNS[idx] in group, f"位置 {idx} 的 {FEATURE_COLUMNS[idx]} 不在当前族"
                idx += 1

    def test_prefix_consistency(self):
        """特征名前缀跟特征族一致 (card_*/cust_*/cdr_*/dev_*/channel_*/iot_*)."""
        for col in FEATURE_COLUMNS:
            assert any(col.startswith(p) for p in ("card_", "cust_", "cdr_", "dev_", "channel_", "iot_")), \
                f"特征 {col} 前缀不符合命名规范"


class TestTrainScriptAlignment:
    """训练脚本 (train_xgb_model.py) 用的特征 key 跟 FEATURE_COLUMNS 对齐."""

    def test_train_roam_code_keys(self):
        """训练脚本的 _ROAM_CODE 跟 feature.py 一致."""
        from app.engine.feature import _ROAM_CODE
        assert _ROAM_CODE == {"归属地": 0, "省内漫游": 1, "省间漫游": 2, "国际漫游": 3}

    def test_risk_msisdn_range(self):
        """训练脚本的风险号段 13800000001-017 (17 张卡)."""
        from scripts.train_xgb_model import RISK_MSISDN_RANGE
        assert RISK_MSISDN_RANGE == (13800000001, 13800000017)

    def test_label_by_risk(self):
        """标签函数: 风险号段 → 1, 其他 → 0."""
        from scripts.train_xgb_model import _label_by_risk
        assert _label_by_risk("13800000001") == 1
        assert _label_by_risk("13800000017") == 1
        assert _label_by_risk("13800000018") == 0
        assert _label_by_risk("13900000000") == 0
        assert _label_by_risk("invalid") == 0
