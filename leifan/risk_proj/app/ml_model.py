from __future__ import annotations

import math
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import xgboost as xgb
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    BlacklistExtra,
    BookingFlight,
    BookingHotel,
    BookingTour,
    OrderInfo,
    OrderPassenger,
    PassengerInfo,
    PaymentAccount,
    UserInfo,
    VisaApplication,
)
from app.scoring import calculate_account_age_days


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_PATH = PROJECT_ROOT / "models" / "travel_risk_xgboost.ubj"

FEATURE_NAMES: tuple[str, ...] = (
    "log_total_amount",
    "is_cross_border",
    "passenger_count",
    "account_age_days",
    "real_name_status",
    "vip_level_ordinal",
    "order_hour_sin",
    "order_hour_cos",
    "days_to_depart",
    "trip_duration_days",
    "order_type_flight",
    "order_type_hotel",
    "order_type_visa",
    "order_type_tour",
    "payment_alipay",
    "payment_bank_card",
    "payment_wechat_pay",
    "payment_active",
    "visa_reject_history_max",
    "visa_current_rejected",
    "flight_ticket_count",
    "flight_segment_count",
    "flight_business_cabin",
    "hotel_room_count",
    "hotel_non_refundable",
    "tour_traveler_count",
    "tour_outbound",
    "blacklisted_passenger_count",
)

VIP_LEVELS = {
    "NORMAL": 0,
    "SILVER": 1,
    "GOLD": 2,
    "PLATINUM": 3,
    "DIAMOND": 4,
}


def resolve_model_path(path: str | Path | None = None) -> Path:
    configured = path or os.getenv("XGBOOST_MODEL_PATH")
    if configured is None:
        return DEFAULT_MODEL_PATH
    candidate = Path(configured)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


@dataclass(frozen=True, slots=True)
class ModelFeatureContext:
    payments: dict[int, PaymentAccount]
    visas_by_order: dict[int, list[VisaApplication]]
    flights_by_order: dict[int, list[BookingFlight]]
    hotels_by_order: dict[int, BookingHotel]
    tours_by_order: dict[int, BookingTour]
    passengers_by_order: dict[int, list[PassengerInfo]]
    active_blacklist: set[str]

    def vector(self, order: OrderInfo, user: UserInfo) -> list[float]:
        payment = self.payments[order.payment_account_id]
        visas = self.visas_by_order.get(order.order_id, [])
        flights = self.flights_by_order.get(order.order_id, [])
        hotel = self.hotels_by_order.get(order.order_id)
        tour = self.tours_by_order.get(order.order_id)
        passengers = self.passengers_by_order.get(order.order_id, [])

        amount = max(float(order.total_amount), 0.0)
        days_to_depart = (
            max((order.depart_date - order.order_time.date()).days, 0)
            if order.depart_date is not None
            else 0
        )
        trip_duration_days = (
            max((order.return_date - order.depart_date).days, 0)
            if order.depart_date is not None and order.return_date is not None
            else 0
        )
        hour_angle = 2 * math.pi * order.order_time.hour / 24
        max_reject_history = max((item.reject_history for item in visas), default=0)
        blacklisted_count = sum(
            passenger.id_number_hash in self.active_blacklist for passenger in passengers
        )

        return [
            math.log1p(amount),
            float(order.is_cross_border),
            float(order.passenger_count),
            float(calculate_account_age_days(user.registered_at, as_of=order.order_time)),
            float(user.real_name_status),
            float(VIP_LEVELS.get(user.vip_level.upper(), 0)),
            math.sin(hour_angle),
            math.cos(hour_angle),
            float(days_to_depart),
            float(trip_duration_days),
            float(order.order_type == "FLIGHT"),
            float(order.order_type == "HOTEL"),
            float(order.order_type == "VISA"),
            float(order.order_type == "TOUR"),
            float(payment.account_type == "ALIPAY"),
            float(payment.account_type == "BANK_CARD"),
            float(payment.account_type == "WECHAT_PAY"),
            float(payment.status == "ACTIVE"),
            float(max_reject_history),
            float(any(item.application_status == "REJECTED" for item in visas)),
            float(sum(item.ticket_count for item in flights)),
            float(len(flights)),
            float(any(item.cabin_class == "BUSINESS" for item in flights)),
            float(hotel.room_count if hotel is not None else 0),
            float(hotel is not None and not hotel.is_refundable),
            float(tour.traveler_count if tour is not None else 0),
            float(tour is not None and tour.route_type == "OUTBOUND"),
            float(blacklisted_count),
        ]


def load_feature_context(
    session: Session, *, as_of: datetime | None = None
) -> ModelFeatureContext:
    reference_time = as_of or datetime.now()
    payments = {
        item.payment_account_id: item for item in session.scalars(select(PaymentAccount))
    }

    visas_by_order: dict[int, list[VisaApplication]] = defaultdict(list)
    for item in session.scalars(select(VisaApplication)):
        visas_by_order[item.order_id].append(item)

    flights_by_order: dict[int, list[BookingFlight]] = defaultdict(list)
    for item in session.scalars(
        select(BookingFlight).order_by(BookingFlight.order_id, BookingFlight.segment_no)
    ):
        flights_by_order[item.order_id].append(item)

    hotels_by_order = {
        item.order_id: item for item in session.scalars(select(BookingHotel))
    }
    tours_by_order = {
        item.order_id: item for item in session.scalars(select(BookingTour))
    }

    passengers_by_order: dict[int, list[PassengerInfo]] = defaultdict(list)
    for order_id, passenger in session.execute(
        select(OrderPassenger.order_id, PassengerInfo)
        .join(PassengerInfo, PassengerInfo.passenger_id == OrderPassenger.passenger_id)
        .order_by(OrderPassenger.order_id, PassengerInfo.passenger_id)
    ):
        passengers_by_order[order_id].append(passenger)

    active_blacklist = set(
        session.scalars(
            select(BlacklistExtra.value_hash).where(
                BlacklistExtra.status == "ACTIVE",
                BlacklistExtra.effective_at <= reference_time,
                (BlacklistExtra.expire_at.is_(None))
                | (BlacklistExtra.expire_at > reference_time),
            )
        )
    )
    return ModelFeatureContext(
        payments=payments,
        visas_by_order=dict(visas_by_order),
        flights_by_order=dict(flights_by_order),
        hotels_by_order=hotels_by_order,
        tours_by_order=tours_by_order,
        passengers_by_order=dict(passengers_by_order),
        active_blacklist=active_blacklist,
    )


@dataclass(frozen=True, slots=True)
class XGBoostRiskModel:
    booster: xgb.Booster
    version: str
    path: Path

    def predict_margin(self, feature_vector: list[float]) -> float:
        matrix = xgb.DMatrix(
            np.asarray([feature_vector], dtype=np.float32),
            feature_names=list(FEATURE_NAMES),
        )
        return float(self.booster.predict(matrix, output_margin=True)[0])


def load_risk_model(path: str | Path | None = None) -> XGBoostRiskModel | None:
    model_path = resolve_model_path(path)
    if not model_path.exists():
        return None
    booster = xgb.Booster()
    booster.load_model(model_path)
    if booster.feature_names and tuple(booster.feature_names) != FEATURE_NAMES:
        raise RuntimeError("XGBoost 模型特征与当前系统不一致，请重新训练模型")
    return XGBoostRiskModel(
        booster=booster,
        version=booster.attr("model_version") or model_path.stem,
        path=model_path,
    )
