"""特征工程接口: 暴露 11 维特征向量说明与三大特征族元数据.

直接复用 app.engine.feature.FEATURE_ORDER 与三大特征族函数, 避免重复定义.
"""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.engine import feature as feat  # noqa: E402

router = APIRouter(prefix="/api", tags=["features"])

# 特征中文名 / 所属族 / 含义 / 取值口径
FEATURE_META: dict[str, dict] = {
    "multi_loan_index":       {"family": "user", "name": "多头借贷指数", "desc": "征信查询与借贷平台数的加权归一", "range": "0~1"},
    "over_query_freq":        {"family": "user", "name": "过度查询频次", "desc": "30天征信查询次数归一", "range": "0~1"},
    "login_brute_freq":       {"family": "user", "name": "登录撞库频控", "desc": "5分钟登录失败次数归一", "range": "0~1"},
    "hist_risk_level":        {"family": "user", "name": "历史风险等级", "desc": "账户/商户历史风险上限 0低1中2高", "range": "0/1/2"},
    "large_amt_flag":         {"family": "order", "name": "大额转账标记", "desc": "金额>=20万记1", "range": "0/1"},
    "disperse_peer_cnt":      {"family": "order", "name": "分散转入对手数", "desc": "近1h对手数归一(上限35)", "range": "0~1"},
    "txn_time_anomaly":       {"family": "order", "name": "交易时间异常度", "desc": "0-6点=1, 7-8/22-23=0.5", "range": "0/0.5/1"},
    "amount_deviation":       {"family": "order", "name": "金额偏离度", "desc": "相对历史均值偏离倍数归一", "range": "0~1"},
    "geo_deviation":          {"family": "address", "name": "地理偏离度", "desc": "异地/IP突变记1", "range": "0/1"},
    "ip_risk_score":          {"family": "address", "name": "IP异常评分", "desc": "黑名单IP=1, 可疑段=0.6", "range": "0~1"},
    "device_fp_consistency":  {"family": "address", "name": "设备指纹一致性", "desc": "一致=1, 新设备=0.5", "range": "0~1"},
}

FAMILY_NAMES = {"user": "用户特征族", "order": "订单特征族", "address": "地址特征族"}


@router.get("/features")
def get_features() -> dict:
    """返回 11 维特征向量说明 + 三大特征族聚合."""
    features = [
        {
            "key": k,
            "name": FEATURE_META[k]["name"],
            "family": FEATURE_META[k]["family"],
            "desc": FEATURE_META[k]["desc"],
            "range": FEATURE_META[k]["range"],
        }
        for k in feat.FEATURE_ORDER
    ]
    families = {
        fid: {
            "name": FAMILY_NAMES[fid],
            "features": [f for f in features if f["family"] == fid],
        }
        for fid in FAMILY_NAMES
    }
    return {
        "feature_order": feat.FEATURE_ORDER,
        "count": len(feat.FEATURE_ORDER),
        "features": features,
        "families": families,
    }


@router.post("/features/compute")
def compute_features(event: dict) -> dict:
    """给定事件 dict, 计算三大特征族与定长向量 (供前端联调/演示)."""
    feats = feat.compute_all_features(event)
    return {
        "features": feats,
        "vector": feat.build_feature_vector(event),
        "features_all": feat.compute_all_features(event),
    }
