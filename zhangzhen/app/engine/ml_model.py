"""XGBoost 可选加载器；任何模型问题都自动降级为纯规则。"""

import logging
from pathlib import Path
from typing import Any

from app.config import settings
from app.engine.feature import FEATURE_COLUMNS


logger = logging.getLogger(__name__)
DEFAULT_MODEL_PATH = Path(__file__).with_name("xgb_model.json")


class XGBoostRiskModel:
    def __init__(self, model_path: Path = DEFAULT_MODEL_PATH) -> None:
        self.model_path = model_path
        self._booster: Any = None
        self._xgb: Any = None
        self._load_attempted = False

    @property
    def is_loaded(self) -> bool:
        return self._booster is not None

    def reset(self) -> None:
        """清空进程内模型缓存，供训练完成或规则纯回放后重新加载。"""

        self._booster = None
        self._xgb = None
        self._load_attempted = False

    def reload(self) -> bool:
        self.reset()
        return self.load()

    def load(self) -> bool:
        if self._load_attempted:
            return self.is_loaded
        self._load_attempted = True
        if not settings.XGB_ENABLED or not self.model_path.exists():
            return False
        try:
            import xgboost as xgb

            booster = xgb.Booster()
            booster.load_model(self.model_path)
            if booster.num_features() != len(FEATURE_COLUMNS):
                raise ValueError(
                    f"模型特征数 {booster.num_features()} 与契约 {len(FEATURE_COLUMNS)} 不一致"
                )
            if booster.feature_names and tuple(booster.feature_names) != FEATURE_COLUMNS:
                raise ValueError("模型特征名称或顺序与 FEATURE_COLUMNS 不一致")
            self._xgb = xgb
            self._booster = booster
            return True
        except Exception:
            logger.exception("XGBoost加载失败，自动降级为纯规则")
            self._booster = None
            return False

    def predict(self, features: dict[str, float]) -> float | None:
        if not self.load():
            return None
        try:
            vector = [[float(features[name]) for name in FEATURE_COLUMNS]]
            matrix = self._xgb.DMatrix(vector, feature_names=list(FEATURE_COLUMNS))
            probability = float(self._booster.predict(matrix)[0])
            return min(max(probability, 0.0), 1.0)
        except Exception:
            logger.exception("XGBoost推理失败，本次评估降级为纯规则")
            return None


ml_model = XGBoostRiskModel()
