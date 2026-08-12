"""
特征注册表.

从 config/features.yaml 加载特征配置, 统一导出特征列名.
"""

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.config import settings

logger = logging.getLogger(__name__)


def _default_config_path() -> Path:
    """特征配置路径, 相对项目根目录."""
    return Path(__file__).resolve().parents[2] / settings.FEATURE_CONFIG_PATH


def load_feature_config(path: str | None = None) -> list[dict[str, Any]]:
    """读取特征配置, 返回启用特征列表."""
    try:
        config_path = Path(path) if path else _default_config_path()
        with config_path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        features = raw.get("features", [])
        enabled = [f for f in features if f.get("enabled", True)]
        logger.info("特征配置加载成功: path=%s total=%d enabled=%d", config_path, len(features), len(enabled))
        return enabled
    except Exception:
        logger.exception("特征配置加载失败: path=%s", path)
        raise


@lru_cache(maxsize=1)
def get_feature_columns() -> tuple[str, ...]:
    """返回启用特征名, 顺序固定."""
    try:
        return tuple(f["name"] for f in load_feature_config())
    except Exception:
        logger.exception("特征列生成失败")
        raise


FEATURE_COLUMNS: list[str] = list(get_feature_columns())


if __name__ == "__main__":
    print(f"启用特征数: {len(FEATURE_COLUMNS)}")
    print("\n".join(FEATURE_COLUMNS))
