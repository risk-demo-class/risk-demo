"""脱敏工具测试 (2026-08-11 P1): mask_value / mask_kwargs / mask_business_row / access log 过滤."""
import logging

from app.masking import (
    MaskQueryStringFilter,
    mask_business_row,
    mask_kwargs,
    mask_value,
)


class TestMaskValue:
    def test_full_mask(self):
        assert mask_value("13800000001", 0, 0) == "****"

    def test_partial_mask_keeps_head_tail(self):
        masked = mask_value("13800000001")  # 保留前2后1
        assert masked.startswith("13")
        assert masked.endswith("1")
        assert "*" in masked

    def test_short_value_fully_masked(self):
        assert mask_value("ab", 2, 1) == "**"


class TestMaskKwargs:
    def test_value_fully_masked(self):
        out = mask_kwargs({"value": "13800000001", "query_type": "user_claims"})
        assert out["value"] == "****"
        assert out["query_type"] == "user_claims"

    def test_user_id_partially_masked(self):
        out = mask_kwargs({"user_id": "RISK001"})
        assert out["user_id"].startswith("RI")
        assert "*" in out["user_id"]

    def test_db_key_passthrough(self):
        out = mask_kwargs({"db": object(), "limit": 10})
        assert "db" in out
        assert out["limit"] == 10


class TestMaskBusinessRow:
    def test_sensitive_fields_masked(self):
        row = {
            "rx_id": "RX_1",
            "diagnosis_name": "原发性高血压",
            "receiver_name": "赵大勇",
            "total_amount": 120.0,
        }
        out = mask_business_row(row)
        assert out["diagnosis_name"] == "****"
        assert out["receiver_name"] == "****"
        assert out["rx_id"] == "RX_1"
        assert out["total_amount"] == 120.0

    def test_empty_sensitive_field_left_alone(self):
        out = mask_business_row({"receiver_name": ""})
        assert out["receiver_name"] == ""


class TestMaskQueryStringFilter:
    def _record(self, args):
        return logging.LogRecord(
            name="uvicorn.access", level=logging.INFO, pathname="", lineno=0,
            msg='%s - "%s %s HTTP/%s" %d', args=args, exc_info=None,
        )

    def test_query_string_masked(self):
        rec = self._record(("1.2.3.4", "GET", "/api/assessments?user_id=U001&phone=138", "1.1", 200))
        assert MaskQueryStringFilter().filter(rec)
        args = rec.args
        assert args[2] == "/api/assessments?<masked>"
        assert "138" not in str(args)

    def test_no_query_string_untouched(self):
        rec = self._record(("1.2.3.4", "GET", "/api/rules", "1.1", 200))
        assert MaskQueryStringFilter().filter(rec)
        assert rec.args[2] == "/api/rules"
