"""ORM 模型注册测试."""

from app.database import Base


def test_all_tables_registered():
    table_names = set(Base.metadata.tables.keys())
    assert "risk_rule" in table_names
    assert "risk_assessment" in table_names
    assert "order_info" in table_names
    assert "booking_hotel" in table_names
    assert "visa_application" in table_names
