"""可重复生成与校验制造业业务事件数据。

主数据和核心单据由 sql/init_business_data.sql 提供；本脚本用于演示增量业务事件造数，
每次执行会先删除自身生成的 PYBE 前缀事件，因此可重复运行且不会重复累积。
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pymysql

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import BusinessEventType, settings
from app.service.validator import validate_event

GENERATED_PREFIX = "PYBE"
TARGET_EVENT_COUNT = 120


def connect() -> pymysql.connections.Connection:
    return pymysql.connect(host=settings.db_host, port=settings.db_port, user=settings.db_user, password=settings.db_password, database=settings.db_name, charset="utf8mb4", autocommit=True)


def validate_database(connection: pymysql.connections.Connection) -> dict[str, int]:
    required = {"plant": 4, "supplier": 8, "material": 20, "work_order": 120, "business_event": 120, "risk_rule": 16, "risk_event": 16}
    with connection.cursor() as cursor:
        counts: dict[str, int] = {}
        for table, minimum in required.items():
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = int(cursor.fetchone()[0])
            counts[table] = count
            if count < minimum:
                raise RuntimeError(f"表 {table} 数据不足：{count} < {minimum}")
        cursor.execute("""SELECT COUNT(*) FROM work_order wo LEFT JOIN sales_order so ON so.sales_order_id = wo.sales_order_id WHERE so.sales_order_id IS NULL""")
        if cursor.fetchone()[0]:
            raise RuntimeError("发现工单缺少销售订单关联")
        cursor.execute("""SELECT COUNT(*) FROM material_issue mi LEFT JOIN inventory inv ON inv.lot_no = mi.lot_no WHERE inv.inventory_id IS NULL""")
        if cursor.fetchone()[0]:
            raise RuntimeError("发现领料记录缺少库存批次关联")
    return counts


def generate_business_events(connection: pymysql.connections.Connection, count: int) -> int:
    event_types = list(BusinessEventType)
    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM business_event WHERE event_id LIKE %s", (f"{GENERATED_PREFIX}%",))
        cursor.execute("SELECT work_order_id FROM work_order ORDER BY work_order_id LIMIT %s", (count,))
        work_orders = [row[0] for row in cursor.fetchall()]
        if len(work_orders) < count:
            raise RuntimeError(f"工单数量不足，无法生成 {count} 条事件")
        rows = []
        for index, work_order_id in enumerate(work_orders, start=1):
            event_type = event_types[(index - 1) % len(event_types)].value
            payload = {"work_order_id": work_order_id, "source": "python_generator", "sequence": index}
            reasons = validate_event(event_type, payload)
            payload["validation_passed"] = not reasons
            payload["validation_reasons"] = reasons
            rows.append((f"{GENERATED_PREFIX}{index:04d}", event_type, "work_order", work_order_id, "MES", "E003", datetime(2026, 8, 12, 8, 0) + timedelta(minutes=index), f"PYTRACE-{index:04d}", __import__("json").dumps(payload, ensure_ascii=False)))
        cursor.executemany("""INSERT INTO business_event (event_id,event_type,entity_type,entity_id,source_system,operator_id,business_at,trace_id,payload_json) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""", rows)
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="生成或校验制造业业务数据")
    parser.add_argument("--count", type=int, default=TARGET_EVENT_COUNT, help="生成业务事件数量，默认 120")
    parser.add_argument("--validate-only", action="store_true", help="只校验初始化业务数据，不新增事件")
    args = parser.parse_args()
    connection = connect()
    try:
        counts = validate_database(connection)
        if args.validate_only:
            print("业务数据校验通过：" + ", ".join(f"{table}={count}" for table, count in counts.items()))
            return
        generated = generate_business_events(connection, args.count)
        print(f"已重复生成 {generated} 条业务事件（前缀 {GENERATED_PREFIX}），随后执行校验。")
        validate_database(connection)
    finally:
        connection.close()


if __name__ == "__main__":
    main()

