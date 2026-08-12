"""
训练 XGBoost 模型.

数据来源: data/travel_risk_train.csv (可用 gen_train_csv.py 生成)
"""

import argparse
import logging
from pathlib import Path

import pandas as pd

from app.config import settings
from app.engine.feature_registry import FEATURE_COLUMNS
from app.engine.ml_model import train_and_save

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def train() -> None:
    """执行训练."""
    try:
        csv_path = PROJECT_ROOT / settings.TRAIN_CSV_PATH
        if not csv_path.exists():
            raise FileNotFoundError(f"训练数据不存在: {csv_path}, 请先运行 gen_train_csv.py")

        df = pd.read_csv(csv_path)
        if "label" not in df.columns:
            raise ValueError("CSV 缺少 label 列")
        y = df["label"].astype(int).to_numpy()
        X = df[list(FEATURE_COLUMNS)].fillna(0).to_numpy(dtype=float)

        if len(df) < settings.XGB_MIN_SAMPLES:
            logger.warning(
                "样本量 %d 小于建议值 %d, 模型可能不稳定",
                len(df),
                settings.XGB_MIN_SAMPLES,
            )

        metrics, model = train_and_save(X, y, feature_names=list(FEATURE_COLUMNS))
        print("=" * 60)
        print("XGBoost 训练结果")
        print("=" * 60)
        for key, value in metrics.items():
            print(f"{key}: {value}")
        print(f"模型已保存: {metrics['model_path']}")
        if metrics.get("is_fake_convergence"):
            print("[WARN] 疑似假收敛, 请检查数据分布并重训")
    except Exception:
        logger.exception("XGBoost 训练失败")
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="训练 XGBoost 模型")
    parser.parse_args()
    train()


if __name__ == "__main__":
    main()
