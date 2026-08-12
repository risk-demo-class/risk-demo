"""训练银行场景的教学 XGBoost 模型并输出验证指标。

该脚本生成带噪声的可复现合成特征，适合在没有历史标签时验证训练/推理链路。
生产模型必须改用脱敏后的真实历史评估数据执行 train_xgb_model.py。
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.engine.ml_model import FEATURE_COLUMNS, train_and_save  # noqa: E402


def build_dataset(n: int = 2500, seed: int = 42) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    X = np.zeros((n, len(FEATURE_COLUMNS)), dtype=np.float32)
    idx = {name: i for i, name in enumerate(FEATURE_COLUMNS)}

    # 客户与正常事件基线。
    X[:, idx["user_credit_score"]] = rng.normal(650, 70, n).clip(350, 850)
    X[:, idx["user_account_age_days"]] = rng.integers(10, 3000, n)
    X[:, idx["user_kyc_level"]] = rng.integers(1, 4, n)
    X[:, idx["user_card_count"]] = rng.integers(1, 6, n)
    X[:, idx["user_transaction_count_30d"]] = rng.poisson(20, n)
    X[:, idx["user_transaction_amount_30d"]] = rng.lognormal(9.3, 0.8, n)
    X[:, idx["user_failed_login_count_24h"]] = rng.poisson(0.4, n)
    X[:, idx["user_loan_application_count_30d"]] = rng.poisson(0.5, n)
    X[:, idx["user_avg_debt_ratio"]] = rng.beta(2, 5, n)
    X[:, idx["user_loan_institution_count_30d"]] = rng.poisson(0.5, n)
    X[:, idx["event_amount"]] = rng.lognormal(7.3, 1.0, n)
    X[:, idx["event_hour"]] = rng.integers(0, 24, n)
    X[:, idx["event_is_night"]] = ((X[:, idx["event_hour"]] < 6)).astype(float)
    X[:, idx["event_is_new_device"]] = rng.binomial(1, 0.08, n)
    X[:, idx["event_device_age_days"]] = rng.integers(0, 1000, n)
    X[:, idx["event_ip_is_proxy"]] = rng.binomial(1, 0.04, n)
    X[:, idx["event_ip_is_tor"]] = rng.binomial(1, 0.01, n)
    X[:, idx["event_geo_mismatch"]] = rng.binomial(1, 0.06, n)
    X[:, idx["event_velocity_1h"]] = rng.poisson(1.2, n)
    X[:, idx["event_distinct_source_cards_1h"]] = rng.integers(1, 3, n)
    X[:, idx["context_card_credit_utilization"]] = rng.beta(2, 5, n)
    X[:, idx["context_loan_amount_income_ratio"]] = rng.gamma(1.2, 1.0, n)
    X[:, idx["context_login_failure_streak"]] = rng.poisson(0.3, n)
    X[:, idx["context_shared_device_user_count"]] = rng.integers(1, 3, n)
    X[:, idx["context_to_card_blacklisted"]] = rng.binomial(1, 0.01, n)

    # 先给一部分样本注入可观测的银行欺诈模式；标签仍由下方组合逻辑生成。
    injected = rng.choice(n, size=int(n * 0.20), replace=False)
    for pattern, rows in enumerate(np.array_split(injected, 7)):
        if pattern == 0:  # 异地大额
            X[rows, idx["event_amount"]] = rng.uniform(55_000, 150_000, len(rows))
            X[rows, idx["event_geo_mismatch"]] = 1
        elif pattern == 1:  # 凌晨密集
            X[rows, idx["event_hour"]] = rng.integers(0, 5, len(rows))
            X[rows, idx["event_is_night"]] = 1
            X[rows, idx["event_velocity_1h"]] = rng.integers(3, 9, len(rows))
        elif pattern == 2:  # 多头借贷
            X[rows, idx["user_loan_institution_count_30d"]] = rng.integers(3, 7, len(rows))
        elif pattern == 3:  # 设备多人共用
            X[rows, idx["context_shared_device_user_count"]] = rng.integers(3, 10, len(rows))
        elif pattern == 4:  # 涉诈收款卡
            X[rows, idx["context_to_card_blacklisted"]] = 1
        elif pattern == 5:  # 新设备 + 代理 IP
            X[rows, idx["event_ip_is_proxy"]] = 1
            X[rows, idx["event_is_new_device"]] = 1
        else:  # 低信用 + 高额度消耗
            X[rows, idx["context_card_credit_utilization"]] = rng.uniform(0.83, 1.10, len(rows))
            X[rows, idx["user_credit_score"]] = rng.uniform(380, 570, len(rows))

    # 标签来自多场景风险信号组合，并加入少量翻转噪声避免完全规则化。
    risk_signal = (
        ((X[:, idx["event_amount"]] > 45_000) & (X[:, idx["event_geo_mismatch"]] == 1))
        | ((X[:, idx["event_is_night"]] == 1) & (X[:, idx["event_velocity_1h"]] >= 3))
        | (X[:, idx["user_loan_institution_count_30d"]] >= 3)
        | (X[:, idx["context_shared_device_user_count"]] >= 3)
        | (X[:, idx["context_to_card_blacklisted"]] == 1)
        | ((X[:, idx["event_ip_is_proxy"]] == 1) & (X[:, idx["event_is_new_device"]] == 1))
        | ((X[:, idx["context_card_credit_utilization"]] > 0.82) & (X[:, idx["user_credit_score"]] < 580))
    )
    y = risk_signal.astype(np.int32)
    flips = rng.choice(n, size=int(n * 0.015), replace=False)
    y[flips] = 1 - y[flips]
    return X, y


def main() -> None:
    X, y = build_dataset()
    metrics, model = train_and_save(
        X,
        y,
        model_path=str(ROOT / "app" / "engine" / "xgb_model.json"),
        num_boost_round=180,
        early_stopping_rounds=20,
        return_model=True,
    )
    importance = model.get_score(importance_type="gain")
    # 报告保存相对路径，项目复制到其他目录后仍然有效。
    metrics["model_path"] = "app/engine/xgb_model.json"
    metrics["top_features"] = sorted(
        importance.items(), key=lambda item: item[1], reverse=True,
    )[:10]
    report_path = ROOT / "docs" / "model_metrics.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    if metrics.get("val_auc", 0) < 0.75 or metrics.get("val_f1", 0) < 0.60:
        raise SystemExit("验证指标未达到教学验收线: val_auc>=0.75 且 val_f1>=0.60")


if __name__ == "__main__":
    main()
