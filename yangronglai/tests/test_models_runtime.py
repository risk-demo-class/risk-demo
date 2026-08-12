from app.engine.model_manager import model_manager


def test_five_registered_models_load_and_score() -> None:
    assert model_manager.ensure_ready()
    status = model_manager.status()
    assert set(status) == {"CARD", "TRANSFER", "LOAN_DEFAULT", "LOAN_FRAUD", "LOGIN"}
    assert all(item["ready"] for item in status.values())
    assert all(item["metrics"]["roc_auc"] >= 0.7 for item in status.values())

    transfer = model_manager.score(
        "TRANSFER",
        {
            "amount": 60000,
            "event_hour": 2,
            "transactions_1h": 4,
            "distinct_from_cards_1h": 4,
            "device_age_days": 1,
            "device_user_count": 2,
            "is_proxy": True,
            "beneficiary_blacklisted": False,
            "current_city": "上海",
            "usual_city": "北京",
        },
    )
    assert transfer is not None
    assert 0 <= transfer.probability <= 1
    assert 0 <= transfer.score <= 100
    assert set(transfer.submodels) == {"TRANSFER"}
