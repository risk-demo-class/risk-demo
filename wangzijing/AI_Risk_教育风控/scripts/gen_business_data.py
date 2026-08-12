"""生成教育行业业务数据，并可写入 MySQL 或导出静态 SQL。

默认生成 65 个用户、20 门课程、180 笔报名订单，以及学习、退费、
认证和设备绑定数据。固定 ``--seed`` 与 ``--anchor`` 时结果完全可复现。

示例：
  python scripts/gen_business_data.py --dry-run
  python scripts/gen_business_data.py --write-sql sql/init_business_data.sql --anchor 2026-08-01T12:00:00
  python scripts/gen_business_data.py
  python scripts/gen_business_data.py --reset --yes
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import random
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    "user_info": (
        "user_id", "name", "role", "student_id_hash", "id_number_hash",
        "real_name_status", "register_at", "account_status",
    ),
    "course": (
        "course_id", "course_name", "category", "price", "teacher_id",
        "total_hours", "course_status",
    ),
    "order_info": (
        "order_id", "user_id", "course_id", "total_amount", "discount_amount",
        "final_amount", "order_status", "channel", "device_id_hash",
        "create_time", "payment_time",
    ),
    "learning_progress": (
        "progress_id", "user_id", "course_id", "order_id", "total_minutes",
        "completion_rate", "last_active_at",
    ),
    "refund_request": (
        "refund_id", "order_id", "user_id", "refund_amount", "reason",
        "refund_status", "apply_time", "processed_time",
    ),
    "identity_verification": (
        "verify_id", "user_id", "verify_type", "document_hash", "verify_result",
        "fail_reason", "submit_time", "review_time",
    ),
    "device_binding": (
        "binding_id", "user_id", "device_id_hash", "ip_hash", "first_seen",
        "last_seen", "is_current",
    ),
}

PRIMARY_KEYS = {
    "user_info": ("user_id",),
    "course": ("course_id",),
    "order_info": ("order_id",),
    "learning_progress": ("progress_id",),
    "refund_request": ("refund_id",),
    "identity_verification": ("verify_id",),
    "device_binding": ("binding_id",),
}

DELETE_ORDER = (
    "device_binding",
    "identity_verification",
    "refund_request",
    "learning_progress",
    "order_info",
    "course",
    "user_info",
)


def _hash(namespace: str, value: str) -> str:
    """对合成标识做 SHA-256，模拟生产中的不可逆脱敏。"""
    return hashlib.sha256(f"education-demo:{namespace}:{value}".encode("utf-8")).hexdigest()


def _money(value: float | str | Decimal) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def build_dataset(seed: int = 202608, anchor: datetime | None = None) -> dict[str, list[dict[str, Any]]]:
    """构造确定性的教育业务数据集。"""
    rng = random.Random(seed)
    anchor = (anchor or datetime.now()).replace(microsecond=0)
    data: dict[str, list[dict[str, Any]]] = {name: [] for name in TABLE_COLUMNS}

    teacher_ids = [f"TEACHER{i:03d}" for i in range(1, 6)]
    normal_ids = [f"EDU{i:03d}" for i in range(1, 41)]
    risk_ids = [f"RISK{i:03d}" for i in range(1, 21)]
    learner_ids = normal_ids + risk_ids

    for index, user_id in enumerate(teacher_ids, start=1):
        data["user_info"].append({
            "user_id": user_id,
            "name": f"演示教师{index:02d}",
            "role": "教师",
            "student_id_hash": None,
            "id_number_hash": _hash("id-number", user_id),
            "real_name_status": "已认证",
            "register_at": anchor - timedelta(days=360 + index * 15),
            "account_status": "正常",
        })

    for index, user_id in enumerate(learner_ids, start=1):
        role = "家长" if user_id in normal_ids[-5:] else "学员"
        verify_failed = user_id in risk_ids[12:16]
        data["user_info"].append({
            "user_id": user_id,
            "name": f"演示{role}{index:03d}",
            "role": role,
            "student_id_hash": None if role == "家长" else _hash("student-id", user_id),
            "id_number_hash": _hash("id-number", user_id),
            "real_name_status": "认证失败" if verify_failed else "已认证",
            "register_at": anchor - timedelta(days=20 + (index * 7) % 320),
            "account_status": "正常",
        })

    categories = ("职业技能", "语言学习", "升学辅导", "编程开发", "艺术素养")
    prices = (399, 699, 999, 1299, 1999, 2999, 3999, 5999, 7999, 9999)
    for index in range(1, 21):
        data["course"].append({
            "course_id": f"COURSE{index:03d}",
            "course_name": f"{categories[(index - 1) % len(categories)]}示范课程{index:02d}",
            "category": categories[(index - 1) % len(categories)],
            "price": _money(prices[(index - 1) % len(prices)]),
            "teacher_id": teacher_ids[(index - 1) % len(teacher_ids)],
            "total_hours": _money(8 + (index % 8) * 4),
            "course_status": "上架" if index < 20 else "下架",
        })

    course_by_id = {row["course_id"]: row for row in data["course"]}
    shared_device = _hash("device", "shared-risk-device")
    order_number = 0
    refund_number = 0

    for learner_index, user_id in enumerate(learner_ids):
        risk_number = int(user_id[-3:]) if user_id.startswith("RISK") else 0
        base_device = shared_device if 9 <= risk_number <= 13 else _hash("device", f"{user_id}-primary")

        for sequence in range(3):
            order_number += 1
            order_id = f"ORD{order_number:05d}"
            course_id = f"COURSE{((learner_index * 3 + sequence) % 20) + 1:03d}"
            course_price = course_by_id[course_id]["price"]
            discount = _money(0 if sequence == 0 else min(200, float(course_price) * 0.08))
            total_amount = course_price
            create_time = anchor - timedelta(
                days=(learner_index * 5 + sequence * 7) % 88,
                hours=(learner_index + sequence * 3) % 20,
            )
            device_hash = base_device
            order_status = "已支付"

            if user_id.startswith("EDU") and (learner_index + sequence) % 29 == 0:
                order_status = "已取消"
            if 1 <= risk_number <= 4 and sequence == 2:
                total_amount = _money(8999)
                discount = _money(0)
                order_status = "已退费"
            elif 5 <= risk_number <= 8:
                order_status = "已退费"
            elif user_id.startswith("EDU") and learner_index % 13 == 0 and sequence == 2:
                order_status = "已退费"
            elif risk_number == 18 and sequence == 1:
                total_amount = _money(6999)
                discount = _money(0)
                create_time = anchor.replace(hour=2, minute=30, second=0)
            elif 17 <= risk_number <= 20 and sequence == 2:
                total_amount = _money(35999 if risk_number == 20 else 12999)
                discount = _money(0)
                create_time = anchor - timedelta(hours=risk_number)
                device_hash = _hash("device", f"{user_id}-new")

            final_amount = total_amount - discount
            payment_time = None if order_status in ("待支付", "已取消") else create_time + timedelta(minutes=5 + sequence * 3)
            data["order_info"].append({
                "order_id": order_id,
                "user_id": user_id,
                "course_id": course_id,
                "total_amount": total_amount,
                "discount_amount": discount,
                "final_amount": final_amount,
                "order_status": order_status,
                "channel": ("网页", "移动端", "线下录入")[(learner_index + sequence) % 3],
                "device_id_hash": device_hash,
                "create_time": create_time,
                "payment_time": payment_time,
            })

            if order_status != "已取消":
                zero_study_refund = 1 <= risk_number <= 4 and sequence == 2
                repeated_refund = 5 <= risk_number <= 8
                if zero_study_refund:
                    completion = Decimal("0.0000")
                    total_minutes = _money(0)
                elif repeated_refund:
                    completion = Decimal("0.0100")
                    total_minutes = _money(5 + sequence)
                else:
                    completion = Decimal(str(round(rng.uniform(0.12, 0.96), 4)))
                    total_hours = course_by_id[course_id]["total_hours"]
                    total_minutes = _money(float(total_hours) * 60 * float(completion))
                data["learning_progress"].append({
                    "progress_id": f"PROG{order_number:05d}",
                    "user_id": user_id,
                    "course_id": course_id,
                    "order_id": order_id,
                    "total_minutes": total_minutes,
                    "completion_rate": completion,
                    "last_active_at": payment_time + timedelta(days=2) if payment_time and total_minutes > 0 else None,
                })

            if order_status == "已退费":
                refund_number += 1
                apply_time = (payment_time or create_time) + timedelta(days=2 + sequence)
                data["refund_request"].append({
                    "refund_id": f"REF{refund_number:04d}",
                    "order_id": order_id,
                    "user_id": user_id,
                    "refund_amount": final_amount,
                    "reason": "购买后未学习申请退费" if 1 <= risk_number <= 4 else "课程安排与预期不符",
                    "refund_status": "已通过",
                    "apply_time": apply_time,
                    "processed_time": apply_time + timedelta(hours=8),
                })

    verify_number = 0
    for learner_index, user_id in enumerate(learner_ids, start=1):
        risk_number = int(user_id[-3:]) if user_id.startswith("RISK") else 0
        attempts = 3 if 13 <= risk_number <= 16 else 1
        for attempt in range(attempts):
            verify_number += 1
            failed = 13 <= risk_number <= 16
            submit_time = anchor - timedelta(days=(learner_index * 3 + attempt) % 70, hours=attempt)
            data["identity_verification"].append({
                "verify_id": f"VER{verify_number:04d}",
                "user_id": user_id,
                "verify_type": "学历认证" if attempt == 0 else "学籍验证",
                "document_hash": _hash("document", f"{user_id}-{attempt}"),
                "verify_result": "失败" if failed else "通过",
                "fail_reason": "材料哈希重复或信息不一致" if failed else None,
                "submit_time": submit_time,
                "review_time": submit_time + timedelta(hours=6),
            })

    binding_number = 0
    for learner_index, user_id in enumerate(learner_ids, start=1):
        risk_number = int(user_id[-3:]) if user_id.startswith("RISK") else 0
        devices = [
            shared_device if 9 <= risk_number <= 13 else _hash("device", f"{user_id}-primary")
        ]
        if 17 <= risk_number <= 20:
            devices.append(_hash("device", f"{user_id}-new"))
        for device_index, device_hash in enumerate(devices):
            binding_number += 1
            is_new = device_index == 1
            first_seen = anchor - (timedelta(hours=risk_number) if is_new else timedelta(days=90 + learner_index))
            data["device_binding"].append({
                "binding_id": binding_number,
                "user_id": user_id,
                "device_id_hash": device_hash,
                "ip_hash": _hash("ip", "shared-risk-ip" if 9 <= risk_number <= 13 else f"{user_id}-ip"),
                "first_seen": first_seen,
                "last_seen": anchor - timedelta(minutes=learner_index),
                "is_current": True,
            })

    validate_dataset(data)
    return data


def validate_dataset(data: dict[str, list[dict[str, Any]]]) -> None:
    """检查主键、外键、脱敏值和五类风险样本是否完整。"""
    for table, keys in PRIMARY_KEYS.items():
        identities = [tuple(row[key] for key in keys) for row in data[table]]
        if len(identities) != len(set(identities)):
            raise ValueError(f"{table} 存在重复主键")

    users = {row["user_id"] for row in data["user_info"]}
    courses = {row["course_id"] for row in data["course"]}
    orders = {row["order_id"]: row for row in data["order_info"]}
    if any(row["teacher_id"] not in users for row in data["course"]):
        raise ValueError("course.teacher_id 存在悬空引用")
    if any(row["user_id"] not in users or row["course_id"] not in courses for row in data["order_info"]):
        raise ValueError("order_info 存在悬空引用")
    for table in ("learning_progress", "refund_request"):
        for row in data[table]:
            order = orders.get(row["order_id"])
            if order is None or order["user_id"] != row["user_id"]:
                raise ValueError(f"{table} 的订单归属不一致")
    for table in ("identity_verification", "device_binding"):
        if any(row["user_id"] not in users for row in data[table]):
            raise ValueError(f"{table} 存在悬空用户引用")

    hash_fields = (
        ("user_info", "student_id_hash"),
        ("user_info", "id_number_hash"),
        ("order_info", "device_id_hash"),
        ("identity_verification", "document_hash"),
        ("device_binding", "device_id_hash"),
        ("device_binding", "ip_hash"),
    )
    for table, field in hash_fields:
        for row in data[table]:
            value = row[field]
            if value is not None and (len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value)):
                raise ValueError(f"{table}.{field} 不是有效 SHA-256 哈希")

    if sum(len(rows) for rows in data.values()) < 100:
        raise ValueError("业务数据总量必须不少于 100 条")

    zero_study_orders = {
        row["order_id"] for row in data["learning_progress"]
        if row["total_minutes"] == 0
    }
    if not any(row["order_id"] in zero_study_orders and row["refund_amount"] >= 5000 for row in data["refund_request"]):
        raise ValueError("缺少零学习高额退费样本")

    refunds_per_user: dict[str, int] = {}
    for row in data["refund_request"]:
        refunds_per_user[row["user_id"]] = refunds_per_user.get(row["user_id"], 0) + 1
    if max(refunds_per_user.values(), default=0) < 3:
        raise ValueError("缺少连续退费样本")

    users_per_device: dict[str, set[str]] = {}
    for row in data["device_binding"]:
        users_per_device.setdefault(row["device_id_hash"], set()).add(row["user_id"])
    if max((len(value) for value in users_per_device.values()), default=0) < 5:
        raise ValueError("缺少设备多账号样本")

    failed_per_user: dict[str, int] = {}
    for row in data["identity_verification"]:
        if row["verify_result"] == "失败":
            failed_per_user[row["user_id"]] = failed_per_user.get(row["user_id"], 0) + 1
    if max(failed_per_user.values(), default=0) < 3:
        raise ValueError("缺少认证连续失败样本")

    approved_refund_amount: dict[str, Decimal] = {}
    for row in data["refund_request"]:
        if row["refund_status"] == "已通过":
            approved_refund_amount[row["user_id"]] = (
                approved_refund_amount.get(row["user_id"], Decimal("0")) + row["refund_amount"]
            )
    if not any(
        refunds_per_user.get(user_id, 0) >= 3 and amount >= 10000
        for user_id, amount in approved_refund_amount.items()
    ):
        raise ValueError("缺少累计退费达到10000元的连环退费样本")

    if not any(
        row["final_amount"] >= 5000 and 1 <= row["create_time"].hour < 5
        for row in data["order_info"]
    ):
        raise ValueError("缺少凌晨大额报名样本")
    if not any(row["final_amount"] >= 30000 for row in data["order_info"]):
        raise ValueError("缺少超高金额报名样本")


def _sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, Decimal)):
        return str(value)
    if isinstance(value, datetime):
        return f"'{value:%Y-%m-%d %H:%M:%S}'"
    escaped = str(value).replace("\\", "\\\\").replace("'", "''")
    return f"'{escaped}'"


def render_sql(data: dict[str, list[dict[str, Any]]], chunk_size: int = 100) -> str:
    """把数据集渲染为可重复执行的 MySQL upsert SQL。"""
    lines = [
        "-- 教育行业业务基础数据；由 scripts/gen_business_data.py 确定性生成。",
        "-- 所有证件、学号、设备和 IP 标识均为合成值的 SHA-256 哈希。",
        "START TRANSACTION;",
        "",
    ]
    for table, columns in TABLE_COLUMNS.items():
        rows = data[table]
        update_columns = [column for column in columns if column not in PRIMARY_KEYS[table]]
        update_clause = ", ".join(
            f"`{column}`=`new_row`.`{column}`" for column in update_columns
        )
        quoted_columns = ", ".join(f"`{column}`" for column in columns)
        for start in range(0, len(rows), chunk_size):
            chunk = rows[start:start + chunk_size]
            values = []
            for row in chunk:
                values.append("(" + ", ".join(_sql_literal(row[column]) for column in columns) + ")")
            lines.append(f"INSERT INTO `{table}` ({quoted_columns}) VALUES")
            lines.append(",\n".join(values))
            lines.append(f"AS `new_row` ON DUPLICATE KEY UPDATE {update_clause};")
            lines.append("")
    lines.extend(("COMMIT;", ""))
    return "\n".join(lines)


def _print_summary(data: dict[str, list[dict[str, Any]]]) -> None:
    print("教育业务数据集校验通过：")
    for table in TABLE_COLUMNS:
        print(f"  {table:<24} {len(data[table]):>4} 条")
    print(f"  {'合计':<24} {sum(len(rows) for rows in data.values()):>4} 条")
    print("风险样本：零学习高额退费 / 连环退费 / 设备多账号 / 认证连续失败 / 新设备大额报名 / 凌晨大额报名 / 超高金额报名")


async def load_database(data: dict[str, list[dict[str, Any]]], reset: bool, yes: bool) -> None:
    if reset and not yes:
        raise SystemExit("--reset 会清空七张教育业务表；确认执行请同时传入 --yes")

    try:
        import aiomysql
        from app.config import settings
    except ImportError as exc:
        raise SystemExit(f"缺少数据库依赖，请先安装 requirements.txt：{exc}") from exc

    connection = await aiomysql.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        db=settings.DB_NAME,
        charset="utf8mb4",
        autocommit=False,
    )
    try:
        async with connection.cursor() as cursor:
            if reset:
                for table in DELETE_ORDER:
                    await cursor.execute(f"DELETE FROM `{table}`")

            for table, columns in TABLE_COLUMNS.items():
                rows = data[table]
                row_placeholders = "(" + ", ".join(["%s"] * len(columns)) + ")"
                quoted_columns = ", ".join(f"`{column}`" for column in columns)
                update_columns = [column for column in columns if column not in PRIMARY_KEYS[table]]
                update_clause = ", ".join(
                    f"`{column}`=`new_row`.`{column}`" for column in update_columns
                )
                for start in range(0, len(rows), 100):
                    chunk = rows[start:start + 100]
                    values_clause = ", ".join([row_placeholders] * len(chunk))
                    statement = (
                        f"INSERT INTO `{table}` ({quoted_columns}) VALUES {values_clause} "
                        f"AS `new_row` ON DUPLICATE KEY UPDATE {update_clause}"
                    )
                    values = tuple(
                        row[column]
                        for row in chunk
                        for column in columns
                    )
                    await cursor.execute(statement, values)
        await connection.commit()
    except Exception:
        await connection.rollback()
        raise
    finally:
        await connection.ensure_closed()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成教育行业风控业务数据")
    parser.add_argument("--seed", type=int, default=202608, help="随机种子，默认 202608")
    parser.add_argument("--anchor", help="时间锚点，ISO 格式；默认当前时间")
    parser.add_argument("--dry-run", action="store_true", help="仅生成并校验，不连接数据库")
    parser.add_argument("--write-sql", type=Path, help="将数据集导出为幂等 SQL 文件")
    parser.add_argument("--reset", action="store_true", help="写库前清空七张教育业务表")
    parser.add_argument("--yes", "-y", action="store_true", help="确认 --reset 的清空操作")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        anchor = datetime.fromisoformat(args.anchor) if args.anchor else datetime.now().replace(microsecond=0)
    except ValueError as exc:
        print(f"时间锚点格式错误：{exc}", file=sys.stderr)
        return 2

    data = build_dataset(seed=args.seed, anchor=anchor)
    _print_summary(data)

    if args.write_sql:
        args.write_sql.parent.mkdir(parents=True, exist_ok=True)
        args.write_sql.write_text(render_sql(data), encoding="utf-8")
        print(f"已写出 SQL：{args.write_sql.resolve()}")

    if not args.dry_run and not args.write_sql:
        asyncio.run(load_database(data, reset=args.reset, yes=args.yes))
        print("数据已写入数据库。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
