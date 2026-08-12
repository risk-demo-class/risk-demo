from __future__ import annotations

import math

from sqlalchemy import select

from app.database import SessionLocal
from app.ml_model import FEATURE_NAMES, load_feature_context, load_risk_model
from app.models import OrderInfo, UserInfo


def test_trained_model_is_loadable_and_predicts_a_finite_margin() -> None:
    model = load_risk_model()
    assert model is not None

    with SessionLocal() as session:
        order = session.scalar(select(OrderInfo).order_by(OrderInfo.order_id).limit(1))
        assert order is not None
        user = session.get(UserInfo, order.user_id)
        assert user is not None
        context = load_feature_context(session)
        vector = context.vector(order, user)

    assert len(vector) == len(FEATURE_NAMES)
    assert all(math.isfinite(value) for value in vector)
    assert math.isfinite(model.predict_margin(vector))
