"""
电信风控系统 - XGBoost 训练脚本 (对齐 ai_risk 训练范式)
======================================================
数据源: telecom 库业务表 (telecom_card/cdr/customer/device/channel/iot/data_usage/billing/group)

训练范式 (跟 ai_risk 一致):
  1. 拉 300 张号卡, 同步算 30 维特征 (对齐 ml_model.FEATURE_COLUMNS)
  2. 标签: idx 1-50 + 290-299 为风险样本 (y=1), 其余为正常 (y=0)
  3. 直接 train_test_split (80/20 stratify), 不做数据增强
  4. train_and_save: 内部完成 80/20 再拆分 + 早停 + 评估
  5. 质量门禁: 样本量 / 正例比例 / 假收敛检测 / val 指标
  6. 输出 train AUC / val AUC / val F1 / 特征重要性 TOP10

跑法: python scripts/train_xgb_model.py
"""
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pymysql

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import settings  # noqa: E402
from app.engine.ml_model import FEATURE_COLUMNS, train_and_save  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

TRAIN_NOW = datetime(2026, 8, 12, 18, 0, 0)

_ROAM_CODE = {"归属地": 0, "省内漫游": 1, "省间漫游": 2, "国际漫游": 3}

# 风险样本: idx 1-50 + idx 290-299 (共 60 张)
RISK_IDX_RANGES = [(1, 50), (290, 299)]


def _label_by_idx(msisdn: str) -> int:
    """用 MSISDN 索引判定风险. idx 1-50 或 290-299 = 风险 (y=1), 其余正常."""
    try:
        idx = int(msisdn[3:])
        for lo, hi in RISK_IDX_RANGES:
            if lo <= idx <= hi:
                return 1
        return 0
    except (ValueError, TypeError):
        return 0


def _compute_features(conn, msisdn: str, now: datetime) -> dict[str, float] | None:
    """同步算 25 维特征 (跟 feature.py 异步版逻辑一致, 对齐 FEATURE_COLUMNS)."""
    f: dict[str, float] = {}
    with conn.cursor() as cur:
        # ---- 号卡 (5) ----
        cur.execute(
            "SELECT open_time, is_iot, intl_call_enabled, roam_status, card_status, "
            "open_province, current_imei, customer_id, open_channel_id "
            "FROM telecom_card WHERE msisdn=%s", (msisdn,),
        )
        card = cur.fetchone()
        if not card:
            return None
        (open_time, is_iot, intl_enabled, roam_status, card_status,
         open_province, current_imei, customer_id, channel_id) = card
        age_days = max((now - open_time).total_seconds() / 86400.0, 0.0) if open_time else 0.0
        f["card_age_days"] = round(age_days, 2)
        f["card_is_iot"] = float(is_iot)
        f["card_intl_enabled"] = float(intl_enabled)
        f["card_roam_type_code"] = float(_ROAM_CODE.get(roam_status, 0))
        f["card_status_normal"] = 1.0 if card_status == "正常" else 0.0

        # ---- 客户 (5) ----
        cur.execute("SELECT face_verify_status, risk_tag FROM telecom_customer WHERE customer_id=%s", (customer_id,))
        cust = cur.fetchone()
        cur.execute("SELECT COUNT(*) FROM telecom_card WHERE customer_id=%s", (customer_id,))
        card_count = float(cur.fetchone()[0] or 0)
        cur.execute("SELECT COUNT(DISTINCT open_channel_id) FROM telecom_card WHERE customer_id=%s", (customer_id,))
        channel_count = float(cur.fetchone()[0] or 0)
        f["cust_card_count"] = card_count
        f["cust_id_multi_card_flag"] = 1.0 if card_count >= 5 else 0.0
        f["cust_face_verify_passed"] = 1.0 if (cust and cust[0] == "通过") else 0.0
        f["cust_risk_tag_high_flag"] = 1.0 if (cust and cust[1] == "高风险") else 0.0
        f["cust_open_channel_count"] = channel_count

        # ---- 通信行为 (8) ----
        h1 = now - timedelta(hours=1)
        h24 = now - timedelta(hours=24)
        cur.execute(
            "SELECT COUNT(*), COUNT(DISTINCT cell_id) FROM telecom_cdr "
            "WHERE calling_no=%s AND start_time>=%s", (msisdn, h1),
        )
        r = cur.fetchone()
        f["cdr_out_count_1h"] = float(r[0] or 0)
        f["cdr_distinct_cell_1h"] = float(r[1] or 0)
        cur.execute("SELECT COUNT(*) FROM telecom_cdr WHERE calling_no=%s AND start_time>=%s", (msisdn, h24))
        f["cdr_out_count_24h"] = float(cur.fetchone()[0] or 0)
        cur.execute("SELECT COUNT(*) FROM telecom_cdr WHERE called_no=%s AND start_time>=%s", (msisdn, h24))
        f["cdr_in_count_24h"] = float(cur.fetchone()[0] or 0)
        cur.execute(
            "SELECT COUNT(*) FROM telecom_cdr WHERE called_no=%s AND roam_type='国际' AND start_time>=%s",
            (msisdn, h24),
        )
        f["cdr_intl_incoming_24h"] = float(cur.fetchone()[0] or 0)
        cur.execute(
            "SELECT COUNT(*), COALESCE(SUM(CASE WHEN duration<10 THEN 1 ELSE 0 END),0), "
            "COALESCE(SUM(CASE WHEN HOUR(start_time)<6 THEN 1 ELSE 0 END),0), COALESCE(AVG(duration),0) "
            "FROM telecom_cdr WHERE calling_no=%s", (msisdn,),
        )
        r = cur.fetchone()
        total = float(r[0] or 0)
        f["cdr_short_call_ratio"] = round(float(r[1] or 0) / total, 4) if total > 0 else 0.0
        f["cdr_night_call_ratio"] = round(float(r[2] or 0) / total, 4) if total > 0 else 0.0
        f["cdr_avg_duration_sec"] = round(float(r[3] or 0), 2)

        # 凌晨 1h 内主叫次数 (R015: 凌晨密集呼叫)
        night_1h = now - timedelta(hours=1)
        cur.execute(
            "SELECT COUNT(*) FROM telecom_cdr "
            "WHERE calling_no=%s AND HOUR(start_time)<6 AND start_time>=%s",
            (msisdn, night_1h),
        )
        f["cdr_night_call_count"] = float(cur.fetchone()[0] or 0)

        # ---- 设备 (3) ----
        cards_on_imei = 0.0
        mismatch = 0.0
        if current_imei:
            cur.execute("SELECT COUNT(*) FROM telecom_card WHERE current_imei=%s", (current_imei,))
            cards_on_imei = float(cur.fetchone()[0] or 0)
            cur.execute(
                "SELECT cell_id FROM telecom_cdr WHERE calling_no=%s ORDER BY start_time DESC LIMIT 1", (msisdn,),
            )
            last = cur.fetchone()
            if last and last[0]:
                cur.execute("SELECT province FROM telecom_cell WHERE cell_id=%s", (last[0],))
                cp = cur.fetchone()
                if cp and cp[0] and open_province and cp[0] != open_province:
                    mismatch = 1.0
        since_30d = now - timedelta(days=30)
        cur.execute(
            "SELECT COUNT(*) FROM telecom_card_device_binding WHERE msisdn=%s AND bind_time>=%s",
            (msisdn, since_30d),
        )
        f["dev_cards_on_imei"] = cards_on_imei
        f["dev_card_imei_mismatch_flag"] = mismatch
        f["dev_binding_changes_30d"] = float(cur.fetchone()[0] or 0)

        # ---- 渠道 (2) ----
        cur.execute("SELECT channel_type FROM telecom_channel WHERE channel_id=%s", (channel_id,))
        ch = cur.fetchone()
        f["channel_is_agent_flag"] = 1.0 if (ch and ch[0] == "代理商") else 0.0
        cur.execute(
            "SELECT COUNT(*) FROM telecom_service_order WHERE channel_id=%s AND order_type='新开户' AND order_time>=%s",
            (channel_id, h1),
        )
        f["channel_open_count_1h"] = float(cur.fetchone()[0] or 0)

        # ---- 物联网 (2) ----
        burst = 0.0
        unbound = 0.0
        if is_iot:
            cur.execute("SELECT bound_device_imei FROM telecom_iot_card WHERE msisdn=%s", (msisdn,))
            iot = cur.fetchone()
            if not iot or not iot[0]:
                unbound = 1.0
            elif current_imei and iot[0] != current_imei:
                unbound = 1.0
            cur.execute(
                "SELECT data_volume_mb FROM telecom_data_usage WHERE msisdn=%s ORDER BY usage_date DESC LIMIT 7",
                (msisdn,),
            )
            rows = cur.fetchall()
            if rows:
                today_vol = float(rows[0][0] or 0)
                hist = [float(r[0] or 0) for r in rows[1:]] if len(rows) > 1 else [today_vol]
                hist_avg = sum(hist) / len(hist) if hist else 0.0
                burst = round(today_vol / hist_avg, 2) if hist_avg > 0 else 0.0
        f["iot_data_burst_ratio"] = burst
        f["iot_card_device_unbound_flag"] = unbound

        # ---- 账单 (2) ----
        cur.execute(
            "SELECT COUNT(*) FROM telecom_billing_record "
            "WHERE msisdn=%s AND bill_type='充值' AND create_time>=%s",
            (msisdn, h1),
        )
        f["bill_recharge_count_1h"] = float(cur.fetchone()[0] or 0)
        cur.execute(
            "SELECT COALESCE(SUM(amount),0) FROM telecom_billing_record "
            "WHERE msisdn=%s AND bill_type='转出'", (msisdn,),
        )
        outflow = float(cur.fetchone()[0] or 0)
        cur.execute(
            "SELECT COALESCE(SUM(amount),0) FROM telecom_billing_record "
            "WHERE msisdn=%s AND bill_type='消费'", (msisdn,),
        )
        consume = float(cur.fetchone()[0] or 0)
        total_out = outflow + consume
        f["bill_outflow_ratio"] = round(outflow / total_out, 4) if total_out > 0 else 0.0

        # ---- 集团 (2) ----
        cur.execute(
            "SELECT group_id FROM telecom_group_customer WHERE customer_id=%s AND group_status='正常'",
            (customer_id,),
        )
        grp = cur.fetchone()
        if grp:
            cur.execute("SELECT COUNT(*) FROM telecom_card WHERE customer_id=%s", (customer_id,))
            sub_count = float(cur.fetchone()[0] or 0)
            cur.execute("SELECT risk_tag FROM telecom_customer WHERE customer_id=%s", (customer_id,))
            cust_tag = cur.fetchone()
            abnormal = 1.0 if sub_count >= 8 and cust_tag and cust_tag[0] in ("高风险", "中风险") else 0.0
        else:
            sub_count = 0.0
            abnormal = 0.0
        f["grp_sub_count"] = sub_count
        f["grp_sub_abnormal_flag"] = abnormal

    return f


def main() -> None:
    logger.info("=" * 60)
    logger.info("电信风控 XGBoost 训练 (对齐 ai_risk 范式)")
    logger.info("  now=%s (对齐造数基准)", TRAIN_NOW)
    logger.info("  风险样本: idx 1-50 + 290-299 (共 60 张)")
    logger.info("=" * 60)

    conn = pymysql.connect(
        host=settings.DB_HOST, port=settings.DB_PORT,
        user=settings.DB_USER, password=settings.DB_PASSWORD,
        database=settings.DB_NAME, charset="utf8mb4",
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT msisdn FROM telecom_card ORDER BY msisdn")
            msisdns = [r[0] for r in cur.fetchall()]
        logger.info("拉取号卡: %d 张", len(msisdns))

        X_list, y_list = [], []
        for msisdn in msisdns:
            feat = _compute_features(conn, msisdn, TRAIN_NOW)
            if feat is None:
                continue
            X_list.append([feat.get(c, 0.0) for c in FEATURE_COLUMNS])
            y_list.append(_label_by_idx(msisdn))
    finally:
        conn.close()

    X = np.array(X_list, dtype=np.float32)
    y = np.array(y_list, dtype=np.int32)
    n_pos = int(y.sum())
    n_total = len(y)
    logger.info("原始样本: n=%d, pos=%d (%.1f%%), neg=%d",
                n_total, n_pos, 100 * n_pos / max(1, n_total), n_total - n_pos)

    if n_total < 50:
        logger.error("样本不足 50 条 (当前 %d), 无法训练", n_total)
        sys.exit(1)
    if n_pos == 0 or n_pos == n_total:
        logger.error("标签全单一, 无法训练. 检查风险画像数据.")
        sys.exit(1)

    # 正例比例质量门禁 (对齐 ai_risk)
    pos_ratio = n_pos / n_total
    if pos_ratio < 0.15:
        logger.warning(
            "正例比例 %.1f%% < 推荐 15%%, 模型可能假收敛. 建议检查风险画像数据",
            100 * pos_ratio,
        )

    # 直接训练 (不做数据增强, 对齐 ai_risk 范式)
    logger.info("=" * 60)
    logger.info("训练参数: num_boost_round=200, early_stopping_rounds=%d, test_size=%.2f",
                settings.XGB_EARLY_STOPPING_ROUNDS, settings.XGB_TEST_SIZE)
    logger.info("=" * 60)

    metrics, model = train_and_save(
        X, y,
        num_boost_round=200,
        early_stopping_rounds=settings.XGB_EARLY_STOPPING_ROUNDS,
        return_model=True,
    )

    # 输出评估结果 (对齐 ai_risk 格式)
    logger.info("=" * 60)
    logger.info("训练完成: n=%d, pos=%d (%.1f%%), neg=%d",
                metrics["n_train"], metrics["n_pos"],
                100 * metrics["pos_ratio"], metrics["n_neg"])
    logger.info("  scale_pos_weight=%.2f (raw=%.2f)", metrics["scale_pos_weight"], metrics["raw_scale_pos_weight"])
    logger.info("  best_iteration=%d (早停监控 %s, 热启动 %d 轮)",
                metrics["best_iteration"], settings.XGB_EARLY_STOP_METRIC, settings.XGB_WARMUP_ROUNDS)
    logger.info("  [全量] AUC=%.4f, F1=%.4f, Acc=%.4f (baseline=%.4f), P=%.4f, R=%.4f",
                metrics["auc"], metrics["f1"], metrics["accuracy"],
                metrics.get("baseline_accuracy", 0.0), metrics["precision"], metrics["recall"])
    if "val_auc" in metrics:
        logger.info("  [验证集] n=%d, val_auc=%.4f, val_f1=%.4f (阈值=%.2f), val_acc=%.4f",
                    metrics["n_val"], metrics["val_auc"], metrics["val_f1"],
                    metrics.get("best_f1_threshold", 0.5), metrics["val_accuracy"])
    logger.info("  模型保存: %s", metrics["model_path"])

    # 假收敛检测 (对齐 ai_risk)
    warnings = []
    if metrics["best_iteration"] < settings.XGB_MIN_BEST_ITER:
        warnings.append(f"best_iter={metrics['best_iteration']} < {settings.XGB_MIN_BEST_ITER}")
    if "val_auc" in metrics and metrics["val_auc"] < settings.XGB_MIN_VAL_AUC:
        warnings.append(f"val_auc={metrics['val_auc']:.3f} < {settings.XGB_MIN_VAL_AUC}")
    if "val_f1" in metrics and metrics["val_f1"] < settings.XGB_MIN_VAL_F1:
        warnings.append(f"val_f1={metrics['val_f1']:.3f} < {settings.XGB_MIN_VAL_F1}")
    if warnings:
        logger.warning("[质量告警] %s", " | ".join(warnings))
    else:
        logger.info("[质量检查] ✓ 通过 (无假收敛迹象)")

    # 特征重要性 TOP 10
    if model is not None:
        importance = model.get_score(importance_type="gain")
        top = sorted(importance.items(), key=lambda x: -x[1])
        logger.info("")
        logger.info("=" * 60)
        logger.info("[特征重要性 TOP %d] (XGBoost gain)", min(10, len(top)))
        logger.info("=" * 60)
        logger.info("  %-30s %-12s %s", "特征名", "重要性", "占比")
        total_gain = sum(v for _, v in top) or 1
        for rank, (feat, score) in enumerate(top[:10], 1):
            bar = "#" * min(40, int(40 * score / (top[0][1] or 1)))
            logger.info("  %2d. %-27s %10.1f  %5.1f%%  %s",
                        rank, feat, score, 100 * score / total_gain, bar)
        logger.info("=" * 60)
        logger.info("Top 3 特征解释 %.1f%% 决策", 100 * sum(v for _, v in top[:3]) / total_gain)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()