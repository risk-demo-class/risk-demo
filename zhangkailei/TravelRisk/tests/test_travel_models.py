from app.database import Base
from app import models  # noqa: F401


def test_all_business_and_risk_tables_registered():
    expected = {
        "travel_user", "travel_order", "passenger_info", "order_passenger",
        "visa_application", "flight_booking", "hotel_booking", "payment_record",
        "travel_blacklist_entry", "risk_rule", "risk_event", "risk_feature",
        "risk_assessment", "risk_case", "risk_blacklist", "risk_user_profile",
        "risk_action_log", "risk_alert",
    }
    assert expected == set(Base.metadata.tables)


def test_sensitive_columns_are_hashes():
    assert "id_number_hash" in Base.metadata.tables["passenger_info"].columns
    assert "payment_account_hash" in Base.metadata.tables["payment_record"].columns
    assert "phone_hash" in Base.metadata.tables["travel_user"].columns
