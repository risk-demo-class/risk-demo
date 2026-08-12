"""从制造业业务表生成可重复的 XGBoost 训练数据。"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pymysql

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
from app.config import settings
from src.features import FEATURE_COLUMNS

AS_OF_DATE = date(2026, 8, 12)
OUTPUT_FILE = PROJECT_ROOT / "data" / "manufacturing_training_samples.csv"

BASE_SQL = """
SELECT wo.work_order_id,
  CASE s.risk_level WHEN 'LOW' THEN 0 WHEN 'MEDIUM' THEN 0.5 ELSE 1 END supplier_risk_level,
  DATEDIFF(s.qualification_expire_at, %s) supplier_qualification_days,
  COALESCE(iqc.defect_qty / NULLIF(iqc.sample_qty, 0), 0) iqc_defect_rate,
  CASE WHEN inv.quality_status IN ('HOLD','FAILED') THEN 1 ELSE 0 END inventory_hold_flag,
  raw.is_critical material_critical_flag,
  mi.issue_qty / NULLIF(wo.planned_qty * 0.25, 0) issue_over_bom_ratio,
  wo.completed_qty / NULLIF(wo.planned_qty, 0) work_order_progress_ratio,
  opr.scrap_qty / NULLIF(opr.good_qty + opr.scrap_qty, 0) scrap_rate,
  ABS(ip.measured_value - ((ip.lsl + ip.usl) / 2)) / NULLIF((ip.usl - ip.lsl) / 2, 0) process_parameter_deviation,
  GREATEST(DATEDIFF(%s, eq.maintenance_due_at), 0) equipment_maintenance_overdue_days,
  GREATEST(DATEDIFF(%s, eq.calibration_due_at), 0) equipment_calibration_overdue_days,
  CASE WHEN eq.status IN ('ALARM','STOPPED') THEN 1 ELSE 0 END equipment_alarm_flag,
  CASE WHEN fg.quality_status IN ('HOLD','FAILED') THEN 1 ELSE 0 END quality_hold_flag,
  CASE WHEN sh.quality_status <> 'PASSED' OR sh.released_by IS NULL THEN 1 ELSE 0 END shipment_release_gap_flag,
  COALESCE(cc.complaint_count, 0) customer_complaint_count_30d,
  COALESCE(cc.claim_amount, 0) complaint_claim_amount
FROM work_order wo
JOIN sales_order so ON so.sales_order_id = wo.sales_order_id
JOIN purchase_order po ON po.purchase_order_id = CONCAT('PO', LPAD(CAST(SUBSTRING(wo.work_order_id, 3) AS UNSIGNED), 4, '0'))
JOIN supplier s ON s.supplier_id = po.supplier_id
JOIN material raw ON raw.material_id = po.material_id
JOIN material_issue mi ON mi.work_order_id = wo.work_order_id
JOIN inventory inv ON inv.lot_no = mi.lot_no
JOIN receipt rc ON rc.purchase_order_id = po.purchase_order_id
JOIN iqc_inspection iqc ON iqc.receipt_id = rc.receipt_id
JOIN operation_report opr ON opr.work_order_id = wo.work_order_id
JOIN ipqc_inspection ip ON ip.work_order_id = wo.work_order_id
JOIN equipment eq ON eq.equipment_id = ip.equipment_id
JOIN finished_goods fg ON fg.work_order_id = wo.work_order_id
JOIN shipment sh ON sh.sales_order_id = so.sales_order_id
LEFT JOIN (SELECT shipment_id, COUNT(*) complaint_count, SUM(claim_amount) claim_amount FROM customer_complaint GROUP BY shipment_id) cc ON cc.shipment_id = sh.shipment_id
ORDER BY wo.work_order_id
"""


def load_base_rows() -> list[dict[str, object]]:
    connection = pymysql.connect(host=settings.db_host, port=settings.db_port, user=settings.db_user, password=settings.db_password, database=settings.db_name, charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor)
    try:
        with connection.cursor() as cursor:
            cursor.execute(BASE_SQL, (AS_OF_DATE, AS_OF_DATE, AS_OF_DATE))
            rows = list(cursor.fetchall())
    finally:
        connection.close()
    if not rows:
        raise RuntimeError("未查询到工单特征，请先运行 scripts/init_db.py。")
    return rows


def base_vector(row: dict[str, object], rng: np.random.Generator) -> np.ndarray:
    values = np.array([float(row.get(name) or 0.0) for name in FEATURE_COLUMNS], dtype=np.float32)
    values[0] = min(values[0], 0.5); values[1] = max(values[1], 30.0); values[2] = min(values[2], 0.03)
    values[3] = 0; values[5] = rng.uniform(0.75, 1.06); values[6] = rng.uniform(0.85, 1.03); values[7] = rng.uniform(0, 0.025)
    values[8] = rng.uniform(0, 0.75); values[9] = min(max(values[9], 0), 1); values[10] = min(max(values[10], 0), 1)
    values[11] = 0; values[12] = 0; values[13] = 0; values[14] = rng.integers(0, 2); values[15] = rng.uniform(0, 1500)
    return values


def inject_risk(values: np.ndarray, scenario: int, rng: np.random.Generator) -> str:
    if scenario == 0:
        values[0]=1; values[1]=-rng.uniform(1,90); values[2]=rng.uniform(.08,.30); return "供应商资质过期与来料质量恶化"
    if scenario == 1:
        values[3]=1; values[4]=1; values[5]=rng.uniform(1.25,1.8); values[7]=rng.uniform(.06,.18); return "未检关键物料领料并超BOM"
    if scenario == 2:
        values[8]=rng.uniform(1.05,1.8); values[12]=1; values[13]=1; return "关键参数越限且质量冻结发运"
    if scenario == 3:
        values[9]=rng.uniform(5,45); values[10]=rng.uniform(5,60); values[11]=1; values[7]=rng.uniform(.04,.12); return "关键设备维护校准逾期并报警"
    if scenario == 4:
        values[14]=rng.integers(3,9); values[15]=rng.uniform(12000,80000); values[2]=rng.uniform(.04,.16); return "重复高额客户投诉"
    values[0]=1; values[1]=-rng.uniform(1,60); values[3]=1; values[5]=rng.uniform(1.2,1.7); values[8]=rng.uniform(1.05,1.7); values[9]=rng.uniform(1,25); values[11]=1; values[13]=1; values[14]=rng.integers(2,7); values[15]=rng.uniform(10000,60000); return "多维叠加高风险"


def main() -> None:
    parser=argparse.ArgumentParser(description="生成制造业风控训练样本")
    parser.add_argument("--samples",type=int,default=1600); parser.add_argument("--positive-ratio",type=float,default=.42); parser.add_argument("--seed",type=int,default=20260812); parser.add_argument("--output",type=Path,default=OUTPUT_FILE)
    args=parser.parse_args()
    if not 0<args.positive_ratio<1: raise ValueError("positive_ratio 必须在 0 和 1 之间")
    rows=load_base_rows(); rng=np.random.default_rng(args.seed); pos_count=round(args.samples*args.positive_ratio); positive_indices=set(rng.choice(args.samples,size=pos_count,replace=False).tolist())
    records=[]
    for index in range(args.samples):
        row=rows[index%len(rows)]; values=base_vector(row,rng); label=int(index in positive_indices); scenario="正常生产"
        if label: scenario=inject_risk(values,int(rng.integers(0,6)),rng)
        record={"sample_id":f"MFG-S{index+1:05d}","source_work_order_id":row["work_order_id"],"label":label,"scenario":scenario}
        record.update({name:round(float(value),6) for name,value in zip(FEATURE_COLUMNS,values)}); records.append(record)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    fields=["sample_id","source_work_order_id","label","scenario",*FEATURE_COLUMNS]
    with args.output.open("w",newline="",encoding="utf-8-sig") as file:
        writer=csv.DictWriter(file,fieldnames=fields); writer.writeheader(); writer.writerows(records)
    print(f"训练样本已生成：{args.output}")
    print(f"样本数：{len(records)}，高风险：{pos_count}，低风险：{len(records)-pos_count}")


if __name__ == "__main__":
    try: main()
    except Exception as error:
        print(f"生成失败：{error}",file=sys.stderr); raise SystemExit(1) from error

