"""模型评估接口: 读取 scripts/eval_history.jsonl 返回 XGBoost 评估数据.

不触发重训, O(n) 逐行读取, 进程内按文件 mtime 缓存.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi import APIRouter

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

router = APIRouter(prefix="/api", tags=["model-eval"])

EVAL_PATH = ROOT / "scripts" / "eval_history.jsonl"

_cache: dict = {"mtime": None, "data": None}


def _load() -> list[dict]:
    """读取 jsonl, 带 mtime 缓存."""
    if not EVAL_PATH.exists():
        return []
    mtime = EVAL_PATH.stat().st_mtime
    if _cache["mtime"] == mtime and _cache["data"] is not None:
        return _cache["data"]
    rows: list[dict] = []
    with EVAL_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    _cache["mtime"] = mtime
    _cache["data"] = rows
    return rows


@router.get("/model-eval")
def get_model_eval() -> dict:
    """返回 BASE / HARD 两组的 AUC/F1 对比与特征重要性 Top-N."""
    rows = _load()
    if not rows:
        return {"rows": [], "base": None, "hard": None, "feature_importance": []}

    base = [r for r in rows if not r.get("hard_negative_aug")]
    hard = [r for r in rows if r.get("hard_negative_aug")]

    def _agg(group: list[dict]) -> dict | None:
        if not group:
            return None
        return {
            "train_auc": round(sum(r["train_auc"] for r in group) / len(group), 4),
            "val_auc": round(sum(r["val_auc"] for r in group) / len(group), 4),
            "val_f1": round(sum(r["val_f1"] for r in group) / len(group), 4),
            "n_runs": len(group),
        }

    # 特征重要性: 取 HARD 组最后一条 (含全部 11 维)
    fi_src = hard[-1] if hard else base[-1]
    fi = fi_src.get("feature_importance", {})
    importance = sorted(
        [{"feature": k, "gain": round(v, 4)} for k, v in fi.items()],
        key=lambda x: x["gain"], reverse=True,
    )

    return {
        "rows": rows,
        "base": _agg(base),
        "hard": _agg(hard),
        "feature_importance": importance,
    }
