"""生成可复现的旅游风控 XGBoost 教学训练集。

样本直接写入 risk_event/risk_feature/risk_assessment，保持与真实七步流水线
相同的宽表训练接口。标签来自旅游风险模式，正例比例固定约 35%。
"""
import argparse
import json
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pymysql

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import settings  # noqa: E402
from app.engine.ml_model import FEATURE_COLUMNS  # noqa: E402

RISK_USERS = [f"RISK{i:03d}" for i in range(1, 6)]
NORMAL_USERS = [f"TRAVEL{i:04d}" for i in range(6, 11)]


def _sample_features(rng: random.Random, positive: bool) -> dict[str, float]:
    """生成一条 25 维旅游特征；正负样本保留少量交叠，避免纯常量标签。"""
    total_orders = rng.randint(1, 40)
    amount = rng.uniform(800, 22000)
    features = {
        "user_total_orders": total_orders,
        "user_orders_30d": rng.randint(0, min(total_orders, 15)),
        "user_orders_7d": rng.randint(0, min(total_orders, 6)),
        "user_total_amount": amount * total_orders * rng.uniform(0.65, 1.15),
        "user_avg_order_amount": amount,
        "user_max_order_amount": amount * rng.uniform(1.0, 2.2),
        "user_refund_count": rng.randint(0, 2),
        "user_postsale_count": rng.randint(0, 1),
        "user_refund_rate": rng.uniform(0, 0.12),
        "user_postsale_rate": rng.uniform(0, 0.12),
        "user_refund_amount": rng.choice([1, 2]),  # 实名状态编码
        "user_cancel_count": rng.randint(0, 2),
        "user_complaint_count": 0,
        "user_address_count": rng.randint(1, 12),
        "order_total_amount": rng.uniform(500, 25000),
        "order_item_count": rng.randint(1, 4),
        "order_sku_count": rng.randint(1, 3),
        "order_discount_amount": rng.randint(15, 1800),
        "order_discount_rate": rng.uniform(0.45, 1.0),
        "order_pay_interval_sec": rng.randint(7, 120),
        "order_is_night": 1 if rng.random() < 0.08 else 0,
        "order_category_count": rng.randint(2, 20),
        "addr_total_count": total_orders,
        "addr_province_count": rng.randint(1, min(total_orders, 8)),
        "addr_is_new": 1 if rng.random() < 0.2 else 0,
    }
    if positive:
        # 随机选择一种真实旅游高风险模式，并叠加两个弱风险信号。
        pattern = rng.randrange(5)
        if pattern == 0:  # 拒签历史
            features["user_postsale_count"] = rng.randint(2, 6)
        elif pattern == 1:  # 多国签证
            features["user_cancel_count"] = rng.randint(3, 7)
        elif pattern == 2:  # 大额跨境游
            features["order_total_amount"] = rng.uniform(52000, 120000)
        elif pattern == 3:  # 黄牛囤票
            features["order_sku_count"] = rng.randint(5, 14)
        else:  # 黑护照
            features["user_complaint_count"] = rng.randint(1, 3)
        features["user_refund_rate"] = rng.uniform(0.18, 0.75)
        features["order_discount_rate"] = rng.uniform(0, 0.28)
        if rng.random() < 0.55:
            features["user_refund_amount"] = 0  # 高风险样本中未实名占比更高
        if rng.random() < 0.45:
            features["order_is_night"] = 1
            features["order_pay_interval_sec"] = rng.randint(0, 6)
    return {name: round(float(features[name]), 4) for name in FEATURE_COLUMNS}


def generate(count: int) -> None:
    """幂等重建带 ``tour_train_`` 前缀的训练样本。"""
    if count < 50:
        raise ValueError("--count 至少为 50，才能进行分层训练和验证")
    rng = random.Random(20260811)
    positive_count = round(count * 0.35)
    labels = [1] * positive_count + [0] * (count - positive_count)
    rng.shuffle(labels)

    connection = pymysql.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        database=settings.DB_NAME,
        charset="utf8mb4",
        autocommit=False,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM risk_assessment WHERE event_id LIKE 'tour_train_%%'")
            cursor.execute("DELETE FROM risk_feature WHERE event_id LIKE 'tour_train_%%'")
            cursor.execute("DELETE FROM risk_event WHERE event_id LIKE 'tour_train_%%'")

            event_rows = []
            feature_rows = []
            assessment_rows = []
            for index, label in enumerate(labels, 1):
                event_id = f"tour_train_{index:06d}"
                assessment_id = f"tour_ast_{index:06d}"
                user_id = rng.choice(RISK_USERS if label else NORMAL_USERS)
                created = datetime.now() - timedelta(
                    days=rng.randint(0, 29), minutes=rng.randint(0, 1439)
                )
                features = _sample_features(rng, bool(label))
                decision = rng.choice(["人工审核", "拒绝"]) if label else rng.choice(["通过", "标记"])
                risk_level = rng.choice(["高", "极高"]) if label else rng.choice(["低", "中"])
                final_score = rng.randint(65, 100) if label else rng.randint(0, 49)

                event_rows.append((
                    event_id, "下单", f"TRAIN_ORDER_{index:06d}", user_id,
                    json.dumps({"synthetic": True, "tourism_event_type": "机票预订"}, ensure_ascii=False),
                    created,
                ))
                assessment_rows.append((
                    assessment_id, event_id, user_id, "[]", 0, final_score,
                    risk_level, decision, None, None, created,
                ))
                for name, value in features.items():
                    entity_type = "用户" if name.startswith("user_") else (
                        "订单" if name.startswith("order_") else "地址"
                    )
                    feature_rows.append((event_id, entity_type, user_id, name, value, created))

            cursor.executemany(
                "INSERT INTO risk_event "
                "(event_id,event_type,event_source_id,user_id,event_data,create_time) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                event_rows,
            )
            cursor.executemany(
                "INSERT INTO risk_feature "
                "(event_id,entity_type,entity_id,feature_name,feature_value,compute_time) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                feature_rows,
            )
            cursor.executemany(
                "INSERT INTO risk_assessment "
                "(assessment_id,event_id,user_id,rule_results,rule_count,final_score,"
                "risk_level,decision,ml_score,ml_decision,create_time) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                assessment_rows,
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    print(
        f"训练数据生成完成: {count} 条，正例 {positive_count} "
        f"({positive_count / count:.1%})，每条 {len(FEATURE_COLUMNS)} 维"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="生成旅游风控 XGBoost 训练数据")
    parser.add_argument("--count", type=int, default=300, help="样本数，默认 300")
    args = parser.parse_args()
    generate(args.count)


if __name__ == "__main__":
    main()
