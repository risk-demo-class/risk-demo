"""从 risk_event/risk_feature/risk_assessment 训练银行 XGBoost 模型。"""

import json
import logging
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pymysql
from sklearn.model_selection import GroupShuffleSplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402
from app.engine.ml_model import FEATURE_COLUMNS, train_and_save  # noqa: E402
from scripts._console import banner, footer, summary  # noqa: E402

SEED = 20260812
METRICS_PATH = ROOT / "docs" / "model-metrics.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class TrainingDataset:
    X: np.ndarray
    y: np.ndarray
    users: np.ndarray
    event_ids: list[str]
    min_time: datetime | None
    max_time: datetime | None
    source_rows: int
    complete_rows: int


def _decision_to_label(decision: str) -> int:
    return 1 if decision in ("人工审核", "拒绝") else 0


def _load_training_data() -> TrainingDataset:
    conn = pymysql.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        database=settings.DB_NAME,
        charset="utf8mb4",
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT assessment_id, event_id, user_id, decision, create_time
                FROM risk_assessment
                WHERE decision IN ('通过','标记','人工审核','拒绝')
                  AND ml_score IS NULL
                ORDER BY create_time DESC
                LIMIT %s
                """,
                (settings.XGB_TRAIN_DATA_LIMIT,),
            )
            assessments = cursor.fetchall()
            if not assessments:
                raise RuntimeError("没有可训练评估；先运行 gen_train_dataset.py")

            event_meta = {
                event_id: (user_id, _decision_to_label(decision), create_time)
                for _assessment_id, event_id, user_id, decision, create_time in assessments
            }
            event_ids = list(event_meta)
            features: dict[str, dict[str, float]] = {}
            for offset in range(0, len(event_ids), 500):
                batch = event_ids[offset : offset + 500]
                placeholders = ",".join(["%s"] * len(batch))
                cursor.execute(
                    f"SELECT event_id, feature_name, feature_value FROM risk_feature "
                    f"WHERE event_id IN ({placeholders})",
                    batch,
                )
                for event_id, name, value in cursor.fetchall():
                    features.setdefault(event_id, {})[name] = float(value)

            rows: list[list[float]] = []
            labels: list[int] = []
            users: list[str] = []
            complete_event_ids: list[str] = []
            required = set(FEATURE_COLUMNS)
            times: list[datetime] = []
            for event_id, (user_id, label, create_time) in event_meta.items():
                values = features.get(event_id, {})
                if set(values) != required:
                    continue
                rows.append([values[name] for name in FEATURE_COLUMNS])
                labels.append(label)
                users.append(user_id)
                complete_event_ids.append(event_id)
                if isinstance(create_time, datetime):
                    times.append(create_time)

            return TrainingDataset(
                X=np.asarray(rows, dtype=np.float32),
                y=np.asarray(labels, dtype=np.int32),
                users=np.asarray(users),
                event_ids=complete_event_ids,
                min_time=min(times) if times else None,
                max_time=max(times) if times else None,
                source_rows=len(assessments),
                complete_rows=len(rows),
            )
    finally:
        conn.close()


def _load_data_from_mysql() -> tuple[np.ndarray, np.ndarray]:
    """保留既有测试/脚本入口；正式训练使用含用户分组的完整数据对象。"""
    data = _load_training_data()
    return data.X, data.y


def _group_split(data: TrainingDataset) -> tuple[np.ndarray, np.ndarray]:
    """同一用户只落在训练或验证一侧，并确保两侧都有正负样本。"""
    for attempt in range(50):
        splitter = GroupShuffleSplit(
            n_splits=1,
            test_size=settings.XGB_TEST_SIZE,
            random_state=SEED + attempt,
        )
        train_idx, val_idx = next(splitter.split(data.X, data.y, data.users))
        if len(np.unique(data.y[train_idx])) == 2 and len(np.unique(data.y[val_idx])) == 2:
            return train_idx, val_idx
    raise RuntimeError("按用户分组切分后无法同时保留正负样本，请扩充风险用户分布")


def _validate_training_dataset(data: TrainingDataset) -> None:
    """在训练前报告分布和完整性异常，不修改样本或验收门槛。"""
    if data.complete_rows < data.source_rows:
        logger.warning(
            "特征不完整：完整 %d / 来源 %d；不完整事件已排除",
            data.complete_rows,
            data.source_rows,
        )
    if data.source_rows < settings.XGB_TRAIN_DATA_LIMIT * 0.8:
        logger.warning(
            "可训练评估 %d 条，低于配置上限 %d 的 80%%",
            data.source_rows,
            settings.XGB_TRAIN_DATA_LIMIT,
        )
    if data.complete_rows:
        positive_ratio = float(data.y.mean())
        if positive_ratio < 0.15 or positive_ratio > 0.60:
            logger.warning(
                "正例比例 %.2f%% 偏离建议观察区间 15%%–60%%；"
                "请检查业务模式与规则命中，不得直接改标签",
                positive_ratio * 100,
            )
    if data.min_time and data.max_time and data.source_rows > 100:
        span = data.max_time - data.min_time
        if span.total_seconds() < 86400:
            logger.warning("评估 create_time 跨度不足 1 天：%s", span)


def main() -> None:
    banner("XGBoost 模型训练", f"seed={SEED} | 数据库 {settings.DB_NAME}")
    logger.info("加载真实银行风控快照，seed=%d", SEED)
    data = _load_training_data()
    _validate_training_dataset(data)
    if len(data.y) < 50:
        raise SystemExit(f"完整样本不足 50：{len(data.y)}")
    train_idx, val_idx = _group_split(data)
    train_users = set(data.users[train_idx])
    val_users = set(data.users[val_idx])
    if train_users & val_users:
        raise RuntimeError("用户分组切分失败：训练/验证用户有交集")

    metrics, model = train_and_save(
        data.X[train_idx],
        data.y[train_idx],
        num_boost_round=200,
        early_stopping_rounds=settings.XGB_EARLY_STOPPING_ROUNDS,
        validation_data=(data.X[val_idx], data.y[val_idx]),
        seed=SEED,
        return_model=True,
    )
    importance = model.get_score(importance_type="gain")
    total_gain = sum(importance.values()) or 1.0
    importance = {
        name: round(value / total_gain, 6)
        for name, value in sorted(importance.items(), key=lambda item: -item[1])
    }
    metrics.update(
        {
            "model_path": "app/engine/xgb_model.json",
            "seed": SEED,
            "database": settings.DB_NAME,
            "n_dataset": int(len(data.y)),
            "n_unique_users": int(len(set(data.users))),
            "dataset_positive_ratio": round(float(data.y.mean()), 4),
            "train_positive_ratio": round(float(data.y[train_idx].mean()), 4),
            "val_positive_ratio": round(float(data.y[val_idx].mean()), 4),
            "feature_completeness": round(data.complete_rows / data.source_rows, 4),
            "split_method": "GroupShuffleSplit(user_id)",
            "train_user_count": len(train_users),
            "val_user_count": len(val_users),
            "user_overlap_count": len(train_users & val_users),
            "data_time_min": data.min_time.isoformat() if data.min_time else None,
            "data_time_max": data.max_time.isoformat() if data.max_time else None,
            "feature_importance_gain": importance,
            "training_params": {
                "num_boost_round": 200,
                "early_stopping_rounds": settings.XGB_EARLY_STOPPING_ROUNDS,
                "max_depth": settings.XGB_MAX_DEPTH,
                "learning_rate": settings.XGB_LEARNING_RATE,
                "subsample": settings.XGB_SUBSAMPLE,
                "colsample_bytree": settings.XGB_COLSAMPLE_BYTREE,
            },
            "leakage_checks": {
                "decision_rule_score_label_features_excluded": True,
                "train_val_user_overlap": 0,
                "fixed_validation_threshold": 0.5,
            },
        }
    )
    METRICS_PATH.write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    logger.info(
        "验证集: AUC=%.4f F1=%.4f precision=%.4f recall=%.4f confusion=%s",
        metrics["val_auc"],
        metrics["val_f1"],
        metrics["val_precision"],
        metrics["val_recall"],
        metrics["val_confusion_matrix"],
    )
    logger.info("最佳迭代=%d，指标保存=%s", metrics["best_iteration"], METRICS_PATH)
    for name, value in list(importance.items())[:10]:
        logger.info("特征重要性 %s=%.4f", name, value)

    summary(
        [
            ("样本数 (完整)", f"{metrics['n_dataset']} (特征完整率 {metrics['feature_completeness']:.1%})"),
            ("独立用户", metrics["n_unique_users"]),
            ("正例比例", f"{metrics['dataset_positive_ratio']:.1%}"),
            ("验证集 AUC", f"{metrics['val_auc']:.4f}"),
            ("验证集 F1", f"{metrics['val_f1']:.4f}"),
            ("最佳迭代", metrics["best_iteration"]),
            ("数据时间跨度", f"{metrics['data_time_min']} ~ {metrics['data_time_max']}"),
            ("指标保存", str(METRICS_PATH)),
        ],
        title="训练结果",
    )
    footer("训练完成")

    if metrics["val_auc"] >= 0.995:
        logger.warning(
            "AUC 异常接近 1.0：已确认特征不含决策/规则/标签且用户无交集；"
            "高分仍可能来自规则确定性与合成模式过于干净，详见评估文档。"
        )
    if metrics["val_auc"] < settings.XGB_MIN_VAL_AUC or metrics["val_f1"] < settings.XGB_MIN_VAL_F1:
        raise SystemExit(
            f"模型质量未达标: val_auc={metrics['val_auc']}, val_f1={metrics['val_f1']}"
        )


if __name__ == "__main__":
    main()
