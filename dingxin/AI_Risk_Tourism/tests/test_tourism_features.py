"""
旅游风控特征测试 (DB-free)
验证 25 维特征清单分组 + 业务表 ORM 关键字段
"""
from app.engine.ml_model import FEATURE_COLUMNS


EXPECTED_USER = [
    "user_total_orders", "user_orders_30d", "user_orders_7d",
    "user_total_amount", "user_avg_order_amount", "user_max_order_amount",
    "user_visa_reject_90d", "user_visa_countries_30d",
    "user_account_age_days", "user_real_name_status", "user_refund_rate",
]
EXPECTED_ORDER = [
    "order_total_amount", "order_is_night", "order_trip_days",
    "order_passenger_count", "order_is_overseas", "order_is_flight",
    "order_booking_count", "order_is_urgent",
]
EXPECTED_TRIP = [
    "trip_passenger_match_rate", "trip_blacklist_passport_count",
    "trip_same_flight_1h", "trip_distinct_passenger_count",
    "trip_visa_apply_30d", "trip_same_hotel_1h",
]


class TestTourismFeatures:
    def test_25_dim_total(self):
        assert len(FEATURE_COLUMNS) == 25

    def test_group_sizes(self):
        assert len(EXPECTED_USER) == 11
        assert len(EXPECTED_ORDER) == 8
        assert len(EXPECTED_TRIP) == 6

    def test_groups_match_feature_columns(self):
        assert FEATURE_COLUMNS == EXPECTED_USER + EXPECTED_ORDER + EXPECTED_TRIP, (
            "FEATURE_COLUMNS 与特征族清单不一致"
        )

    def test_business_models_key_fields(self):
        """旅游业务表关键字段存在性 (R001-R034 依赖的字段)."""
        from app.models_business import (
            BookingFlight, BookingHotel, OrderInfo, OrderRefund,
            PassengerInfo, UserInfo, VisaApplication,
        )
        tables = {
            "user_info": [c.name for c in UserInfo.__table__.columns],
            "order_info": [c.name for c in OrderInfo.__table__.columns],
            "passenger_info": [c.name for c in PassengerInfo.__table__.columns],
            "visa_application": [c.name for c in VisaApplication.__table__.columns],
            "booking_flight": [c.name for c in BookingFlight.__table__.columns],
            "booking_hotel": [c.name for c in BookingHotel.__table__.columns],
            "order_refund": [c.name for c in OrderRefund.__table__.columns],
        }
        assert "real_name_status" in tables["user_info"]
        assert "account_age_days" in tables["user_info"]
        assert "dest_country" in tables["order_info"]
        assert "depart_date" in tables["order_info"]
        assert "passenger_count" in tables["order_info"]
        assert "id_number" in tables["passenger_info"]
        assert "reject_history" in tables["visa_application"]
        assert "flight_no" in tables["booking_flight"]
        assert "hotel_id" in tables["booking_hotel"]
        assert "refund_id" in tables["order_refund"]


class TestFeatureMeta:
    """规则编辑器特征元数据 (FEATURE_META) 校验."""

    def test_meta_count_and_alignment(self):
        from app.engine.feature import FEATURE_META
        assert len(FEATURE_META) == 25, f"特征元数据应为 25 条, 实际 {len(FEATURE_META)}"
        assert [m["field"] for m in FEATURE_META] == FEATURE_COLUMNS, (
            "FEATURE_META 字段顺序必须与 FEATURE_COLUMNS 一致"
        )

    def test_meta_field_unique(self):
        from app.engine.feature import FEATURE_META
        fields = [m["field"] for m in FEATURE_META]
        assert len(set(fields)) == 25, "特征元数据字段不能重复"

    def test_meta_required_keys(self):
        from app.engine.feature import FEATURE_META
        for m in FEATURE_META:
            assert m["field"] and m["label"], f"元数据缺字段/标签: {m}"
            assert m["type"] in ("int", "binary", "ratio"), (
                f"{m['field']} 类型非法: {m['type']}"
            )
