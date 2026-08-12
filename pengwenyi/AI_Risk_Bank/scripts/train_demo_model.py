"""
银行风控系统 - 教学场景 XGBoost 演示模型训练 (银行版)

【目的】
  不依赖 DB, 纯 numpy 合成 2000 样本, 训练一个针对 12 规则 + 48 特征的合理 XGBoost 模型.
  训完保存到 app/engine/xgb_model.json, run_app.py 启动时直接加载.

【为什么需要这个脚本】
  教学演示时如果不方便造真实评估数据, 用合成数据快速演示"训练 → 保存 → 加载 → 推理"全链路.
  合成样本对齐银行 4 大场景的 48 维特征分布 (用户/转账/登录/贷款/信用卡).

【6 种高风险模式】
  1. 低信用分大额交易 (R015: credit_score < 500 + 大额)
  2. 代理IP异地大额转账 (R001/R025: 异地 + geo_risk)
  3. 高负债大额申贷 (R010: debt_ratio > 0.6 + 大额)
  4. 夜间密集转账 (R002: is_night + 1h_count)
  5. 多卡归集 (R008: 1h_into_count >= 3)
  6. 混合高风险 (上面多种特征都偏高)

【用法】
  python scripts/train_demo_model.py                    # 默认 2000 样本, 训 200 轮
  python scripts/train_demo_model.py --n 5000            # 5000 样本
  python scripts/train_demo_model.py --model-path ml_models/xgb_demo.json  # 自定义保存路径
"""
import argparse
import os
import random
import sys

# UTF-8 stdout
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# 把项目根目录加到 sys.path, 这样能 import app.*
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import numpy as np
import xgboost as xgb
from sklearn.model_selection import train_test_split

from app.config import settings
from app.engine.ml_model import FEATURE_COLUMNS


# ============================================================
# 6 种高风险模式 + 1 种正常用户模式
# 跟 feature.py 48 维特征一一对应, 跟 12 条银行规则的触发条件对得上
# ============================================================

# 48 维特征顺序 (跟 FEATURE_COLUMNS 一致)
FEATURE_NAMES = FEATURE_COLUMNS
N_FEATURES = len(FEATURE_NAMES)
assert N_FEATURES == 48, f"必须是 48 维特征, 实际 {N_FEATURES}"


def _gen_low_credit_high_amount(rng: random.Random) -> np.ndarray:
    """模式 1: 低信用分大额交易 (触发 R015 低信用分大额交易 / R030 黑卡拦截)"""
    return np.array([
        rng.uniform(300, 500),    # user_credit_score  ← 低
        rng.uniform(1, 2),        # user_kyc_level (L1~L2)
        rng.uniform(7, 90),       # user_register_days (新客)
        rng.uniform(50000, 500000),  # user_total_txn_amount  ← 高
        rng.uniform(10, 100),     # user_total_txn_count
        rng.uniform(2000, 10000), # user_avg_txn_amount  ← 高
        rng.uniform(20000, 150000),  # user_max_txn_amount  ← 高
        rng.uniform(0, 2),        # user_total_loan_count
        rng.uniform(0.1, 0.4),    # user_debt_ratio
        rng.uniform(3000, 8000),  # user_monthly_income
        rng.uniform(1, 3),        # user_card_count
        rng.uniform(0.1, 0.6),    # user_credit_utilization  ← 偏高
        rng.uniform(0, 2),        # user_failed_login_7d
        rng.uniform(1, 3),        # user_device_count
        rng.uniform(1, 3),        # user_city_count
        rng.uniform(20000, 150000),  # txn_amount  ← 大额
        0.0 if rng.random() < 0.7 else 1.0,  # txn_is_night
        rng.uniform(0, 2),        # txn_1h_count
        rng.uniform(0, 50000),    # txn_1h_amount
        rng.uniform(0, 1),        # txn_city_match (异地?)
        rng.uniform(0, 1),        # txn_geo_risk (代理?)
        rng.uniform(0, 1),        # txn_to_card_black
        rng.uniform(0, 1),        # txn_1h_into_count
        rng.uniform(1, 3),        # txn_device_user_count
        1.0,                      # login_success
        0.0,                      # login_is_night
        0.0,                      # login_1h_count
        0.0,                      # login_city_match
        0.0,                      # login_geo_risk
        0.0,                      # login_device_new
        1.0,                      # login_device_user_count
        rng.uniform(0, 1),        # loan_amount
        rng.uniform(0, 1),        # loan_term_months
        0.0,                      # loan_debt_ratio
        0.0,                      # loan_monthly_income
        0.0,                      # loan_month_count
        0.0,                      # loan_3m_count
        0.0,                      # loan_apply_gap_days
        0.0,                      # loan_amount_income_ratio
        0.0,                      # loan_geo_risk
        rng.uniform(5000, 50000), # card_amount  ← 大额消费
        0.0 if rng.random() < 0.8 else 1.0,  # card_is_night
        rng.uniform(5000, 20000), # card_credit_limit (低额度)
        rng.uniform(0.5, 1.5),    # card_utilization  ← 刷爆
        rng.uniform(5, 30),       # card_7d_txn_count  ← 高频
        rng.uniform(20000, 150000),  # card_7d_txn_amount  ← 高
        rng.uniform(1, 3),        # card_geo_count_7d
        rng.uniform(0, 1),        # card_device_new
    ], dtype=np.float32)


def _gen_proxy_ip_transfer(rng: random.Random) -> np.ndarray:
    """模式 2: 代理IP异地大额转账 (触发 R001 异地大额转账 / R025 IP代理)"""
    return np.array([
        rng.uniform(500, 700),    # user_credit_score
        1.0,                      # user_kyc_level
        rng.uniform(90, 365),     # user_register_days (老客)
        rng.uniform(10000, 100000),  # user_total_txn_amount
        rng.uniform(5, 50),       # user_total_txn_count
        rng.uniform(500, 5000),   # user_avg_txn_amount
        rng.uniform(30000, 150000),  # user_max_txn_amount
        rng.uniform(0, 1),        # user_total_loan_count
        rng.uniform(0.1, 0.3),    # user_debt_ratio
        rng.uniform(5000, 15000), # user_monthly_income
        rng.uniform(1, 2),        # user_card_count
        rng.uniform(0.1, 0.4),    # user_credit_utilization
        rng.uniform(0, 1),        # user_failed_login_7d
        rng.uniform(1, 2),        # user_device_count
        rng.uniform(1, 2),        # user_city_count
        rng.uniform(50000, 150000),  # txn_amount  ← 大额 (R001 条件 >5万)
        0.0 if rng.random() < 0.8 else 1.0,  # txn_is_night
        rng.uniform(0, 2),        # txn_1h_count
        rng.uniform(0, 60000),    # txn_1h_amount
        1.0,                      # txn_city_match  ← 异地 (R001)
        1.0,                      # txn_geo_risk  ← 代理IP (R025)
        rng.uniform(0, 1),        # txn_to_card_black
        rng.uniform(0, 1),        # txn_1h_into_count
        rng.uniform(1, 2),        # txn_device_user_count
        1.0,                      # login_success
        0.0,                      # login_is_night
        0.0,                      # login_1h_count
        0.0,                      # login_city_match
        0.0,                      # login_geo_risk
        0.0,                      # login_device_new
        1.0,                      # login_device_user_count
        rng.uniform(0, 1),        # loan_amount
        rng.uniform(0, 1),        # loan_term_months
        0.0,                      # loan_debt_ratio
        0.0,                      # loan_monthly_income
        0.0,                      # loan_month_count
        0.0,                      # loan_3m_count
        0.0,                      # loan_apply_gap_days
        0.0,                      # loan_amount_income_ratio
        0.0,                      # loan_geo_risk
        rng.uniform(3000, 20000), # card_amount
        0.0,                      # card_is_night
        rng.uniform(10000, 50000),  # card_credit_limit
        rng.uniform(0.1, 0.4),    # card_utilization
        rng.uniform(2, 8),        # card_7d_txn_count
        rng.uniform(5000, 40000), # card_7d_txn_amount
        rng.uniform(1, 2),        # card_geo_count_7d
        0.0,                      # card_device_new
    ], dtype=np.float32)


def _gen_high_debt_loan(rng: random.Random) -> np.ndarray:
    """模式 3: 高负债大额申贷 (触发 R010 高负债大额申贷 / R012 信贷申请突击)"""
    return np.array([
        rng.uniform(350, 550),    # user_credit_score  ← 低
        1.0,                      # user_kyc_level
        rng.uniform(30, 200),     # user_register_days
        rng.uniform(20000, 200000),  # user_total_txn_amount
        rng.uniform(5, 40),       # user_total_txn_count
        rng.uniform(500, 5000),   # user_avg_txn_amount
        rng.uniform(5000, 50000), # user_max_txn_amount
        rng.uniform(2, 6),        # user_total_loan_count  ← 高 (R012)
        rng.uniform(0.6, 0.9),    # user_debt_ratio  ← 高负债 (R010)
        rng.uniform(3000, 8000),  # user_monthly_income  ← 收入低
        rng.uniform(1, 3),        # user_card_count
        rng.uniform(0.5, 1.5),    # user_credit_utilization
        rng.uniform(0, 2),        # user_failed_login_7d
        rng.uniform(1, 3),        # user_device_count
        rng.uniform(1, 2),        # user_city_count
        rng.uniform(1000, 10000), # txn_amount
        0.0,                      # txn_is_night
        rng.uniform(0, 1),        # txn_1h_count
        rng.uniform(0, 10000),    # txn_1h_amount
        0.0,                      # txn_city_match
        0.0,                      # txn_geo_risk
        0.0,                      # txn_to_card_black
        0.0,                      # txn_1h_into_count
        1.0,                      # txn_device_user_count
        1.0,                      # login_success
        0.0,                      # login_is_night
        0.0,                      # login_1h_count
        0.0,                      # login_city_match
        0.0,                      # login_geo_risk
        0.0,                      # login_device_new
        1.0,                      # login_device_user_count
        rng.uniform(100000, 500000),  # loan_amount  ← 大额 (R010)
        rng.uniform(12, 36),      # loan_term_months
        rng.uniform(0.6, 0.9),    # loan_debt_ratio  ← 高负债
        rng.uniform(3000, 8000),  # loan_monthly_income
        rng.uniform(2, 5),        # loan_month_count  ← 突击 (R012)
        rng.uniform(2, 8),        # loan_3m_count
        rng.uniform(1, 30),       # loan_apply_gap_days  ← 间隔短
        rng.uniform(5, 30),       # loan_amount_income_ratio  ← 高 (R010 条件 >=5)
        rng.uniform(0, 1),        # loan_geo_risk
        rng.uniform(1000, 8000),  # card_amount
        0.0,                      # card_is_night
        rng.uniform(5000, 30000), # card_credit_limit
        rng.uniform(0.3, 0.8),    # card_utilization
        rng.uniform(2, 10),       # card_7d_txn_count
        rng.uniform(3000, 30000), # card_7d_txn_amount
        rng.uniform(1, 2),        # card_geo_count_7d
        0.0,                      # card_device_new
    ], dtype=np.float32)


def _gen_night_high_freq(rng: random.Random) -> np.ndarray:
    """模式 4: 凌晨密集转账 (触发 R002 凌晨密集操作 / R008 多卡归集)"""
    return np.array([
        rng.uniform(500, 650),    # user_credit_score
        1.0,                      # user_kyc_level
        rng.uniform(60, 400),     # user_register_days
        rng.uniform(10000, 100000),  # user_total_txn_amount
        rng.uniform(10, 80),      # user_total_txn_count  ← 高频
        rng.uniform(500, 3000),   # user_avg_txn_amount
        rng.uniform(10000, 50000),  # user_max_txn_amount
        rng.uniform(0, 2),        # user_total_loan_count
        rng.uniform(0.2, 0.5),    # user_debt_ratio
        rng.uniform(5000, 15000), # user_monthly_income
        rng.uniform(2, 4),        # user_card_count  ← 多卡
        rng.uniform(0.3, 0.8),    # user_credit_utilization
        rng.uniform(0, 1),        # user_failed_login_7d
        rng.uniform(2, 4),        # user_device_count  ← 多设备
        rng.uniform(1, 3),        # user_city_count
        rng.uniform(1000, 30000), # txn_amount
        1.0,                      # txn_is_night  ← 凌晨 (R002)
        rng.uniform(3, 8),        # txn_1h_count  ← 密集 (R002)
        rng.uniform(20000, 150000),  # txn_1h_amount  ← 1h 大额
        rng.uniform(0, 1),        # txn_city_match
        rng.uniform(0, 1),        # txn_geo_risk
        rng.uniform(0, 1),        # txn_to_card_black
        rng.uniform(2, 6),        # txn_1h_into_count  ← 归集 (R008)
        rng.uniform(1, 3),        # txn_device_user_count
        1.0,                      # login_success
        rng.uniform(0, 1),        # login_is_night
        0.0,                      # login_1h_count
        0.0,                      # login_city_match
        0.0,                      # login_geo_risk
        0.0,                      # login_device_new
        1.0,                      # login_device_user_count
        rng.uniform(0, 1),        # loan_amount
        rng.uniform(0, 1),        # loan_term_months
        0.0,                      # loan_debt_ratio
        0.0,                      # loan_monthly_income
        0.0,                      # loan_month_count
        0.0,                      # loan_3m_count
        0.0,                      # loan_apply_gap_days
        0.0,                      # loan_amount_income_ratio
        0.0,                      # loan_geo_risk
        rng.uniform(2000, 15000), # card_amount
        0.5 if rng.random() < 0.5 else 1.0,  # card_is_night
        rng.uniform(10000, 40000),  # card_credit_limit
        rng.uniform(0.4, 1.0),    # card_utilization
        rng.uniform(5, 20),       # card_7d_txn_count
        rng.uniform(10000, 80000),  # card_7d_txn_amount
        rng.uniform(1, 2),        # card_geo_count_7d
        0.0,                      # card_device_new
    ], dtype=np.float32)


def _gen_abnormal_login(rng: random.Random) -> np.ndarray:
    """模式 5: 深夜异常登录 (触发 R003 深夜异常登录 / R005 新设备)"""
    return np.array([
        rng.uniform(450, 600),    # user_credit_score
        1.0,                      # user_kyc_level
        rng.uniform(10, 180),     # user_register_days
        rng.uniform(5000, 50000), # user_total_txn_amount
        rng.uniform(3, 30),       # user_total_txn_count
        rng.uniform(300, 3000),   # user_avg_txn_amount
        rng.uniform(3000, 20000), # user_max_txn_amount
        rng.uniform(0, 1),        # user_total_loan_count
        rng.uniform(0.2, 0.5),    # user_debt_ratio
        rng.uniform(4000, 10000), # user_monthly_income
        rng.uniform(1, 2),        # user_card_count
        rng.uniform(0.2, 0.6),    # user_credit_utilization
        rng.uniform(3, 10),       # user_failed_login_7d  ← 失败多 (R003)
        rng.uniform(2, 5),        # user_device_count  ← 多设备
        rng.uniform(2, 5),        # user_city_count  ← 多城市
        rng.uniform(1000, 30000), # txn_amount
        0.5,                      # txn_is_night
        rng.uniform(0, 2),        # txn_1h_count
        rng.uniform(0, 30000),    # txn_1h_amount
        rng.uniform(0, 1),        # txn_city_match
        1.0,                      # txn_geo_risk  ← 代理IP
        rng.uniform(0, 1),        # txn_to_card_black
        rng.uniform(0, 2),        # txn_1h_into_count
        rng.uniform(1, 3),        # txn_device_user_count
        0.0,                      # login_success  ← 失败
        1.0,                      # login_is_night  ← 深夜 (R003)
        rng.uniform(2, 6),        # login_1h_count  ← 密集尝试
        rng.uniform(0, 1),        # login_city_match
        1.0,                      # login_geo_risk  ← 代理
        1.0,                      # login_device_new  ← 新设备 (R005)
        rng.uniform(1, 3),        # login_device_user_count
        rng.uniform(0, 1),        # loan_amount
        rng.uniform(0, 1),        # loan_term_months
        0.0,                      # loan_debt_ratio
        0.0,                      # loan_monthly_income
        0.0,                      # loan_month_count
        0.0,                      # loan_3m_count
        0.0,                      # loan_apply_gap_days
        0.0,                      # loan_amount_income_ratio
        0.0,                      # loan_geo_risk
        rng.uniform(1000, 8000),  # card_amount
        0.3,                      # card_is_night
        rng.uniform(8000, 30000), # card_credit_limit
        rng.uniform(0.2, 0.5),    # card_utilization
        rng.uniform(2, 8),        # card_7d_txn_count
        rng.uniform(3000, 20000), # card_7d_txn_amount
        rng.uniform(1, 2),        # card_geo_count_7d
        1.0,                      # card_device_new  ← 新设备 (R005)
    ], dtype=np.float32)


def _gen_mixed_high_risk(rng: random.Random) -> np.ndarray:
    """模式 6: 混合高风险 (低信用分 + 代理IP + 高负债 + 夜间 + 黑卡 都偏高)"""
    return np.array([
        rng.uniform(300, 480),    # user_credit_score  ← 低
        1.0,                      # user_kyc_level
        rng.uniform(7, 60),       # user_register_days  ← 新客
        rng.uniform(50000, 400000),  # user_total_txn_amount
        rng.uniform(20, 100),     # user_total_txn_count
        rng.uniform(1000, 8000),  # user_avg_txn_amount
        rng.uniform(20000, 150000),  # user_max_txn_amount
        rng.uniform(2, 5),        # user_total_loan_count
        rng.uniform(0.6, 0.9),    # user_debt_ratio  ← 高负债
        rng.uniform(3000, 6000),  # user_monthly_income  ← 低收入
        rng.uniform(2, 5),        # user_card_count  ← 多卡
        rng.uniform(0.8, 2.0),    # user_credit_utilization  ← 刷爆
        rng.uniform(3, 10),       # user_failed_login_7d
        rng.uniform(3, 6),        # user_device_count  ← 多设备
        rng.uniform(2, 5),        # user_city_count  ← 多城市
        rng.uniform(30000, 150000),  # txn_amount  ← 大额
        1.0,                      # txn_is_night  ← 凌晨
        rng.uniform(3, 8),        # txn_1h_count  ← 密集
        rng.uniform(50000, 250000),  # txn_1h_amount
        1.0,                      # txn_city_match  ← 异地
        1.0,                      # txn_geo_risk  ← 代理
        rng.uniform(0.5, 1.0),    # txn_to_card_black  ← 黑卡
        rng.uniform(3, 6),        # txn_1h_into_count  ← 归集
        rng.uniform(2, 5),        # txn_device_user_count  ← 多人共用
        0.0,                      # login_success
        1.0,                      # login_is_night
        rng.uniform(3, 8),        # login_1h_count
        rng.uniform(0, 1),        # login_city_match
        1.0,                      # login_geo_risk
        1.0,                      # login_device_new
        rng.uniform(2, 6),        # login_device_user_count
        rng.uniform(150000, 500000),  # loan_amount  ← 大额申贷
        rng.uniform(12, 36),      # loan_term_months
        rng.uniform(0.6, 0.9),    # loan_debt_ratio
        rng.uniform(3000, 6000),  # loan_monthly_income
        rng.uniform(3, 6),        # loan_month_count  ← 突击
        rng.uniform(3, 10),       # loan_3m_count
        rng.uniform(1, 10),       # loan_apply_gap_days
        rng.uniform(8, 30),       # loan_amount_income_ratio
        1.0,                      # loan_geo_risk
        rng.uniform(10000, 50000),  # card_amount
        1.0,                      # card_is_night
        rng.uniform(5000, 15000), # card_credit_limit  ← 低额度
        rng.uniform(1.0, 2.5),    # card_utilization  ← 严重超限
        rng.uniform(10, 40),      # card_7d_txn_count  ← 高频
        rng.uniform(30000, 200000),  # card_7d_txn_amount
        rng.uniform(2, 5),        # card_geo_count_7d
        1.0,                      # card_device_new
    ], dtype=np.float32)


def _gen_normal_user(rng: random.Random) -> np.ndarray:
    """正常用户 (低风险, 通过/标记)."""
    return np.array([
        rng.uniform(650, 800),    # user_credit_score  ← 高信用
        2.0,                      # user_kyc_level (L2+)
        rng.uniform(365, 1500),   # user_register_days  ← 老客
        rng.uniform(5000, 50000), # user_total_txn_amount
        rng.uniform(3, 20),       # user_total_txn_count
        rng.uniform(200, 2000),   # user_avg_txn_amount
        rng.uniform(1000, 10000), # user_max_txn_amount  ← 低
        rng.uniform(0, 1),        # user_total_loan_count
        rng.uniform(0.1, 0.35),   # user_debt_ratio  ← 低负债
        rng.uniform(8000, 30000), # user_monthly_income  ← 收入稳定
        rng.uniform(1, 2),        # user_card_count
        rng.uniform(0.1, 0.3),    # user_credit_utilization  ← 低
        rng.uniform(0, 1),        # user_failed_login_7d  ← 无失败
        rng.uniform(1, 2),        # user_device_count  ← 设备少
        rng.uniform(1, 2),        # user_city_count  ← 城市少
        rng.uniform(100, 5000),   # txn_amount  ← 小额
        0.0 if rng.random() < 0.9 else 1.0,  # txn_is_night  ← 白天
        rng.uniform(0, 1),        # txn_1h_count
        rng.uniform(0, 5000),     # txn_1h_amount
        0.0,                      # txn_city_match  ← 常用城市
        0.0,                      # txn_geo_risk  ← 正常IP
        0.0,                      # txn_to_card_black
        0.0,                      # txn_1h_into_count
        1.0,                      # txn_device_user_count  ← 专人设备
        1.0,                      # login_success
        0.0,                      # login_is_night
        rng.uniform(0, 1),        # login_1h_count
        0.0,                      # login_city_match
        0.0,                      # login_geo_risk
        0.0,                      # login_device_new  ← 老设备
        1.0,                      # login_device_user_count
        rng.uniform(0, 1),        # loan_amount
        rng.uniform(0, 1),        # loan_term_months
        0.0,                      # loan_debt_ratio
        0.0,                      # loan_monthly_income
        rng.uniform(0, 1),        # loan_month_count
        rng.uniform(0, 1),        # loan_3m_count
        0.0,                      # loan_apply_gap_days
        0.0,                      # loan_amount_income_ratio
        0.0,                      # loan_geo_risk
        rng.uniform(500, 5000),   # card_amount
        0.0,                      # card_is_night
        rng.uniform(20000, 100000),  # card_credit_limit  ← 高额度
        rng.uniform(0.05, 0.25),  # card_utilization  ← 低
        rng.uniform(1, 5),        # card_7d_txn_count
        rng.uniform(500, 8000),   # card_7d_txn_amount
        1.0,                      # card_geo_count_7d  ← 单一城市
        0.0,                      # card_device_new
    ], dtype=np.float32)


# 6 种正例模式 + 1 种负例
POSITIVE_PATTERNS = [
    _gen_low_credit_high_amount, _gen_proxy_ip_transfer, _gen_high_debt_loan,
    _gen_night_high_freq, _gen_abnormal_login, _gen_mixed_high_risk,
]
NEGATIVE_PATTERN = _gen_normal_user


def gen_synthetic_dataset(n: int = 2000, pos_ratio: float = 0.5, seed: int = 42):
    """生成合成训练数据集.

    Args:
        n: 总样本数
        pos_ratio: 正例比例 (默认 0.5)
        seed: 随机种子

    Returns:
        X: (N, 48) float32
        y: (N,) int (0/1)
    """
    rng = random.Random(seed)
    np.random.seed(seed)

    n_pos = int(n * pos_ratio)
    n_neg = n - n_pos

    # 正例: 6 种模式轮换
    X_pos = np.zeros((n_pos, N_FEATURES), dtype=np.float32)
    for i in range(n_pos):
        pattern = POSITIVE_PATTERNS[i % len(POSITIVE_PATTERNS)]
        X_pos[i] = pattern(rng)

    # 负例: 1 种模式
    X_neg = np.zeros((n_neg, N_FEATURES), dtype=np.float32)
    for i in range(n_neg):
        X_neg[i] = NEGATIVE_PATTERN(rng)

    X = np.vstack([X_pos, X_neg])
    y = np.concatenate([np.ones(n_pos, dtype=np.int32), np.zeros(n_neg, dtype=np.int32)])

    # 乱序
    idx = np.random.permutation(n)
    return X[idx], y[idx]


def train_xgboost(X: np.ndarray, y: np.ndarray, num_boost_round: int = 200):
    """训练 XGBoost (用 ml_model.py 的同款超参, 保持一致)."""
    # 80/20 stratify
    X_tr, X_val, y_tr, y_val = train_test_split(
        X, y, test_size=settings.XGB_TEST_SIZE, stratify=y, random_state=42,
    )

    # DMatrix (XGBoost 2.x 必须)
    dtrain = xgb.DMatrix(X_tr, label=y_tr, feature_names=FEATURE_NAMES)
    dval = xgb.DMatrix(X_val, label=y_val, feature_names=FEATURE_NAMES)

    # 训练参数 (跟 ml_model.py 一致, 但简化版)
    params = {
        "objective": "binary:logistic",
        "eval_metric": ["logloss", "auc"],
        "max_depth": 6,
        "learning_rate": 0.1,
        "min_child_weight": 3,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "reg_alpha": 0.1,
        "reg_lambda": 1.0,
        "seed": 42,
        "tree_method": "hist",
    }

    print(f"\n[训练] {len(y_tr)} 训练 / {len(y_val)} 验证 (80/20 stratify)")
    print(f"  正例比例: {y_tr.sum()/len(y_tr):.2%} (训练) / {y_val.sum()/len(y_val):.2%} (验证)")

    booster = xgb.train(
        params,
        dtrain,
        num_boost_round=num_boost_round,
        evals=[(dtrain, "train"), (dval, "val")],
        early_stopping_rounds=10,
        verbose_eval=20,
    )

    # 评估
    y_pred_prob = booster.predict(xgb.DMatrix(X_val, feature_names=FEATURE_NAMES))
    y_pred = (y_pred_prob >= 0.5).astype(int)

    tp = int(np.sum((y_pred == 1) & (y_val == 1)))
    fp = int(np.sum((y_pred == 1) & (y_val == 0)))
    fn = int(np.sum((y_pred == 0) & (y_val == 1)))
    tn = int(np.sum((y_pred == 0) & (y_val == 0)))

    from sklearn.metrics import roc_auc_score, f1_score
    val_auc = roc_auc_score(y_val, y_pred_prob)
    val_f1 = f1_score(y_val, y_pred)
    val_acc = (tp + tn) / len(y_val)

    print(f"\n[验证集]")
    print(f"  AUC = {val_auc:.4f} {'OK' if val_auc > 0.85 else 'WARN (推荐 > 0.85)'}")
    print(f"  F1  = {val_f1:.4f} {'OK' if val_f1 > 0.6 else 'WARN (推荐 > 0.6)'}")
    print(f"  Acc = {val_acc:.4f}")
    print(f"  Confusion: TP={tp} FP={fp} FN={fn} TN={tn}")
    print(f"  Best iter: {booster.best_iteration}")

    return booster, val_auc, val_f1


def main():
    parser = argparse.ArgumentParser(
        description="教学场景 XGBoost 演示模型训练 (不依赖 DB, 纯合成数据)"
    )
    parser.add_argument("--n", type=int, default=2000, help="合成样本数 (默认 2000)")
    parser.add_argument("--pos-ratio", type=float, default=0.5, help="正例比例 (默认 0.5)")
    parser.add_argument("--num-boost-round", type=int, default=200, help="XGBoost 迭代轮数 (默认 200)")
    parser.add_argument("--model-path", type=str,
                        default=os.path.join(PROJECT_ROOT, "app", "engine", "xgb_model.json"),
                        help="模型保存路径 (默认 app/engine/xgb_model.json)")
    parser.add_argument("--seed", type=int, default=42, help="随机种子 (默认 42)")
    args = parser.parse_args()

    print("=" * 70)
    print("教学场景 XGBoost 演示模型训练 (银行版)")
    print("=" * 70)
    print(f"样本数: {args.n} (正例 {args.pos_ratio*100:.0f}% / 负例 {(1-args.pos_ratio)*100:.0f}%)")
    print(f"模型保存: {args.model_path}")
    print("=" * 70)

    # 1. 生成合成数据
    print(f"\n[1/3] 生成 {args.n} 合成样本 (6 种银行高风险模式 + 1 种正常模式)...")
    X, y = gen_synthetic_dataset(n=args.n, pos_ratio=args.pos_ratio, seed=args.seed)
    print(f"  X.shape={X.shape}, 正例={int(y.sum())} ({y.mean():.2%})")

    # 2. 训练
    print("\n[2/3] 训练 XGBoost...")
    booster, val_auc, val_f1 = train_xgboost(X, y, num_boost_round=args.num_boost_round)

    # 3. 保存
    print(f"\n[3/3] 保存模型到 {args.model_path}...")
    os.makedirs(os.path.dirname(args.model_path), exist_ok=True)
    booster.save_model(args.model_path)
    size_kb = os.path.getsize(args.model_path) / 1024
    print(f"  模型文件: {size_kb:.1f} KB")

    print("\n" + "=" * 70)
    print("训练完成!")
    print(f"  val_auc = {val_auc:.4f} {'OK' if val_auc > 0.85 else '< 0.85 警告'}")
    print(f"  val_f1  = {val_f1:.4f} {'OK' if val_f1 > 0.6 else '< 0.6 警告'}")
    print("=" * 70)
    print("下一步:")
    print("  python run_app.py                    # 启动 Web 服务, 自动加载此模型")
    print("  浏览器访问 http://localhost:8000       # 风险检查页能看到 XGBoost 评分")
    print("=" * 70)


if __name__ == "__main__":
    main()
