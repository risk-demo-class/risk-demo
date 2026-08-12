"""生成教育行业业务样例数据。

默认只生成 ``sql/init_business_data.sql``，不连接数据库。使用固定随机种子和
显式 anchor 可得到字节级一致的 SQL；使用 ``--apply`` 可将生成结果写入 MySQL。

示例：
    python scripts/gen_business_data.py
    python scripts/gen_business_data.py --anchor 2026-08-11T12:00:00
    python scripts/gen_business_data.py --apply --db ecs
"""

from __future__ import annotations

import argparse
import hashlib
import os
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Sequence


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT_DIR / "sql" / "init_business_data.sql"
DEFAULT_SEED = 20260811


TABLE_COLUMNS = {
    "user_info": (
        "user_id", "name", "role", "student_id", "id_card_hash",
        "real_name_status", "guardian_consent_status", "register_at",
        "device_id", "is_active", "create_time", "update_time",
    ),
    "course": (
        "course_id", "name", "category", "price", "teacher_id",
        "total_hours", "target_role", "status", "create_time",
    ),
    "order_info": (
        "order_id", "user_id", "course_id", "total_amount",
        "discount_amount", "study_goal", "expected_finish_days", "status",
        "order_time", "payment_time", "pay_channel", "payment_account_hash",
        "create_time",
    ),
    "learning_progress": (
        "progress_id", "order_id", "user_id", "course_id", "total_minutes",
        "completion_rate", "last_active_at", "device_id", "update_time",
    ),
    "refund_request": (
        "refund_id", "order_id", "reason", "study_minutes_before_refund",
        "refund_amount", "status", "refund_account_hash",
        "is_original_route", "apply_time", "complete_time",
    ),
    "live_reward": (
        "reward_id", "user_id", "teacher_id", "live_session_id",
        "reward_amount", "device_id", "guardian_consent_snapshot",
        "payment_account_hash", "status", "reward_time",
    ),
    "blacklist_extra": (
        "entry_id", "entry_type", "entry_value", "reason", "expire_at",
        "is_active", "create_time",
    ),
}


@dataclass(frozen=True)
class BusinessDataset:
    anchor: datetime
    seed: int
    tables: dict[str, list[dict[str, Any]]]

    @property
    def total_rows(self) -> int:
        return sum(len(rows) for rows in self.tables.values())

    @property
    def event_rows(self) -> int:
        return sum(
            len(self.tables[name])
            for name in ("order_info", "learning_progress", "refund_request", "live_reward")
        )

    def counts(self) -> dict[str, int]:
        return {name: len(rows) for name, rows in self.tables.items()}


def stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_dataset(anchor: datetime, seed: int = DEFAULT_SEED) -> BusinessDataset:
    rng = random.Random(seed)
    tables = {name: [] for name in TABLE_COLUMNS}

    surnames = "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜"
    given_names = (
        "晨曦", "子涵", "浩然", "欣怡", "宇轩", "雨桐", "思源", "佳宁",
        "明远", "若溪", "嘉懿", "梓萱", "博文", "可欣", "睿哲", "语彤",
    )

    def person_name(index: int) -> str:
        return surnames[index % len(surnames)] + given_names[index % len(given_names)]

    def add_user(
        user_id: str,
        role: str,
        *,
        registered_days_ago: int,
        device_id: str | None,
        student_id: str | None = None,
        guardian_status: str = "不适用",
        name_index: int = 0,
    ) -> None:
        register_at = anchor - timedelta(days=registered_days_ago, hours=rng.randint(0, 20))
        tables["user_info"].append(
            {
                "user_id": user_id,
                "name": person_name(name_index),
                "role": role,
                "student_id": student_id,
                "id_card_hash": stable_hash(f"demo-id-card:{user_id}"),
                "real_name_status": "已认证",
                "guardian_consent_status": guardian_status,
                "register_at": register_at,
                "device_id": device_id,
                "is_active": True,
                "create_time": register_at,
                "update_time": register_at,
            }
        )

    # 5 名老师、5 名家长、60 名普通学生。
    for i in range(1, 6):
        add_user(
            f"T{i:03d}", "老师", registered_days_ago=900 + i * 20,
            device_id=f"DEV_TEACHER_{i:03d}", name_index=i,
        )
    for i in range(1, 6):
        add_user(
            f"P{i:03d}", "家长", registered_days_ago=500 + i * 10,
            device_id=f"DEV_PARENT_{i:03d}", name_index=10 + i,
        )
    for i in range(1, 61):
        add_user(
            f"U{i:04d}", "学生", registered_days_ago=30 + (i * 7) % 700,
            device_id=f"DEV_NORMAL_{i:04d}", student_id=f"STU{i:06d}",
            guardian_status="已同意" if i % 3 == 0 else "不适用",
            name_index=20 + i,
        )

    # 风险组 1：同设备批量新账号刷报名。
    for i in range(1, 7):
        add_user(
            f"RISK_BRUSH_{i:03d}", "学生", registered_days_ago=1,
            device_id="DEV_RISK_BRUSH_SHARED", student_id=f"RB{i:06d}",
            guardian_status="已同意", name_index=100 + i,
        )

    # 风险组 2：同设备代理学习。
    for i in range(1, 7):
        add_user(
            f"RISK_PROXY_{i:03d}", "学生", registered_days_ago=45 + i,
            device_id="DEV_RISK_PROXY_SHARED", student_id=f"RP{i:06d}",
            guardian_status="已同意", name_index=120 + i,
        )

    # 风险组 3/4/5：连环退费、大额连报、异常直播消费。
    for i in range(1, 4):
        add_user(
            f"RISK_REFUND_{i:03d}", "学生", registered_days_ago=120,
            device_id=f"DEV_RISK_REFUND_{i:03d}", student_id=f"RR{i:06d}",
            guardian_status="已同意", name_index=140 + i,
        )
    add_user(
        "RISK_BIG_001", "学生", registered_days_ago=3,
        device_id="DEV_RISK_BIG_001", student_id="RBIG000001",
        guardian_status="已同意", name_index=150,
    )
    add_user(
        "RISK_LIVE_001", "学生", registered_days_ago=5,
        device_id="DEV_RISK_LIVE_001", student_id="RLIVE00001",
        guardian_status="待确认", name_index=151,
    )

    course_specs = (
        ("C001", "Python 零基础入门", "编程", "899.00", "T001", "40.00"),
        ("C002", "大模型应用开发", "人工智能", "2999.00", "T001", "60.00"),
        ("C003", "高等数学精讲", "升学", "1299.00", "T002", "48.00"),
        ("C004", "英语口语训练", "语言", "1599.00", "T003", "36.00"),
        ("C005", "家庭教育方法", "家庭教育", "699.00", "T004", "20.00"),
        ("C006", "教师数字化教学", "教师发展", "1999.00", "T005", "30.00"),
        ("C007", "数据分析实战", "数据科学", "3299.00", "T001", "54.00"),
        ("C008", "考研英语全程班", "升学", "4599.00", "T003", "120.00"),
        ("C009", "算法竞赛进阶", "编程", "4800.00", "T002", "80.00"),
        ("C010", "人工智能就业班", "人工智能", "6800.00", "T001", "160.00"),
        ("C011", "全栈工程师训练营", "编程", "9800.00", "T005", "200.00"),
        ("C012", "大模型项目就业营", "人工智能", "12800.00", "T001", "220.00"),
    )
    for course_id, name, category, price, teacher_id, total_hours in course_specs:
        target_role = "家长" if course_id == "C005" else "老师" if course_id == "C006" else "学生"
        tables["course"].append(
            {
                "course_id": course_id,
                "name": name,
                "category": category,
                "price": Decimal(price),
                "teacher_id": teacher_id,
                "total_hours": Decimal(total_hours),
                "target_role": target_role,
                "status": "上架",
                "create_time": anchor - timedelta(days=365),
            }
        )

    price_by_course = {
        row["course_id"]: row["price"] for row in tables["course"]
    }
    teacher_by_course = {
        row["course_id"]: row["teacher_id"] for row in tables["course"]
    }

    def add_order(
        order_id: str,
        user_id: str,
        course_id: str,
        order_time: datetime,
        *,
        discount: Decimal = Decimal("0.00"),
        status: str = "已支付",
    ) -> None:
        total = price_by_course[course_id]
        tables["order_info"].append(
            {
                "order_id": order_id,
                "user_id": user_id,
                "course_id": course_id,
                "total_amount": total,
                "discount_amount": discount,
                "study_goal": "提升职业技能",
                "expected_finish_days": 120,
                "status": status,
                "order_time": order_time,
                "payment_time": order_time + timedelta(minutes=3) if status != "待支付" else None,
                "pay_channel": rng.choice(("微信", "支付宝", "银行卡")),
                "payment_account_hash": stable_hash(f"pay-account:{user_id}"),
                "create_time": order_time,
            }
        )

    def add_progress(
        progress_id: str,
        order_id: str,
        user_id: str,
        course_id: str,
        *,
        minutes: int,
        completion_rate: Decimal,
        device_id: str,
        active_at: datetime,
    ) -> None:
        tables["learning_progress"].append(
            {
                "progress_id": progress_id,
                "order_id": order_id,
                "user_id": user_id,
                "course_id": course_id,
                "total_minutes": minutes,
                "completion_rate": completion_rate,
                "last_active_at": active_at,
                "device_id": device_id,
                "update_time": active_at,
            }
        )

    # 140 笔普通报名及对应进度。
    for i in range(1, 141):
        user_num = ((i - 1) % 60) + 1
        user_id = f"U{user_num:04d}"
        course_id = f"C{((i * 5) % 12) + 1:03d}"
        order_time = anchor - timedelta(days=1 + (i * 11) % 170, hours=i % 18)
        order_id = f"ORD_N{i:04d}"
        discount = Decimal(str((i % 4) * 50)).quantize(Decimal("0.01"))
        add_order(order_id, user_id, course_id, order_time, discount=discount)
        minutes = 60 + (i * 47) % 3000
        rate = min(Decimal("100.00"), Decimal(minutes) / Decimal("30"))
        add_progress(
            f"PROG_N{i:04d}", order_id, user_id, course_id,
            minutes=minutes, completion_rate=rate.quantize(Decimal("0.01")),
            device_id=f"DEV_NORMAL_{user_num:04d}",
            active_at=min(anchor, order_time + timedelta(days=10, minutes=minutes % 300)),
        )

    # 批量刷报名：6 个一天内注册账号、同设备、同课程、2 小时内集中下单。
    for i in range(1, 7):
        user_id = f"RISK_BRUSH_{i:03d}"
        order_id = f"ORD_BRUSH_{i:03d}"
        order_time = anchor - timedelta(hours=2, minutes=10 * i)
        add_order(order_id, user_id, "C001", order_time)
        add_progress(
            f"PROG_BRUSH_{i:03d}", order_id, user_id, "C001",
            minutes=10 + i, completion_rate=Decimal("0.50"),
            device_id="DEV_RISK_BRUSH_SHARED", active_at=anchor - timedelta(minutes=i),
        )

    # 代理学习：6 个账号的学习进度来自同一设备。
    for i in range(1, 7):
        user_id = f"RISK_PROXY_{i:03d}"
        order_id = f"ORD_PROXY_{i:03d}"
        order_time = anchor - timedelta(days=20 + i)
        add_order(order_id, user_id, "C002", order_time)
        add_progress(
            f"PROG_PROXY_{i:03d}", order_id, user_id, "C002",
            minutes=1200 + i * 50, completion_rate=Decimal("80.00"),
            device_id="DEV_RISK_PROXY_SHARED", active_at=anchor - timedelta(minutes=i * 2),
        )

    # 连环 0 学时退费：每个风险用户 4 单、90 天内 4 次、累计金额远超 10000。
    refund_counter = 1
    high_courses = ("C009", "C010", "C011", "C012")
    for user_index in range(1, 4):
        user_id = f"RISK_REFUND_{user_index:03d}"
        for course_index, course_id in enumerate(high_courses, 1):
            order_id = f"ORD_REFUND_{user_index:02d}_{course_index:02d}"
            order_time = anchor - timedelta(days=10 * course_index + user_index)
            add_order(order_id, user_id, course_id, order_time, status="已退费")
            minutes = (course_index + user_index) % 4
            add_progress(
                f"PROG_REFUND_{user_index:02d}_{course_index:02d}",
                order_id, user_id, course_id, minutes=minutes,
                completion_rate=Decimal("0.00"),
                device_id=f"DEV_RISK_REFUND_{user_index:03d}",
                active_at=order_time + timedelta(minutes=minutes),
            )
            apply_time = order_time + timedelta(hours=2)
            tables["refund_request"].append(
                {
                    "refund_id": f"REF_RISK_{refund_counter:04d}",
                    "order_id": order_id,
                    "reason": "购买后立即申请退费",
                    "study_minutes_before_refund": minutes,
                    "refund_amount": price_by_course[course_id],
                    "status": "已退款",
                    "refund_account_hash": stable_hash(f"pay-account:{user_id}"),
                    "is_original_route": True,
                    "apply_time": apply_time,
                    "complete_time": apply_time + timedelta(hours=8),
                }
            )
            refund_counter += 1

    # 正常退费样本：已学习、有合理原因、次数低。
    for i in range(1, 13):
        order = tables["order_info"][i * 5]
        progress = next(
            row for row in tables["learning_progress"] if row["order_id"] == order["order_id"]
        )
        amount = (order["total_amount"] - order["discount_amount"]) * Decimal("0.50")
        tables["refund_request"].append(
            {
                "refund_id": f"REF_NORMAL_{i:04d}",
                "order_id": order["order_id"],
                "reason": "学习计划调整",
                "study_minutes_before_refund": progress["total_minutes"],
                "refund_amount": amount.quantize(Decimal("0.01")),
                "status": "已通过",
                "refund_account_hash": order["payment_account_hash"],
                "is_original_route": True,
                "apply_time": min(anchor, order["order_time"] + timedelta(days=15)),
                "complete_time": None,
            }
        )

    # 1 小时累计大额连报：4 笔总额超过 3 万元。
    for i, course_id in enumerate(("C009", "C010", "C011", "C012"), 1):
        order_id = f"ORD_BIG_{i:03d}"
        order_time = anchor - timedelta(minutes=50 - i * 10)
        add_order(order_id, "RISK_BIG_001", course_id, order_time)
        add_progress(
            f"PROG_BIG_{i:03d}", order_id, "RISK_BIG_001", course_id,
            minutes=0, completion_rate=Decimal("0.00"),
            device_id="DEV_RISK_BIG_001", active_at=order_time,
        )

    # 直播异常消费用户先生成一笔课程报名和进度。
    live_order_time = anchor - timedelta(days=2)
    add_order("ORD_LIVE_001", "RISK_LIVE_001", "C002", live_order_time)
    add_progress(
        "PROG_LIVE_001", "ORD_LIVE_001", "RISK_LIVE_001", "C002",
        minutes=30, completion_rate=Decimal("2.00"),
        device_id="DEV_RISK_LIVE_001", active_at=anchor - timedelta(hours=1),
    )

    # 60 条正常直播打赏。
    for i in range(1, 61):
        user_num = ((i * 7) % 60) + 1
        course_id = f"C{((i * 3) % 12) + 1:03d}"
        tables["live_reward"].append(
            {
                "reward_id": f"REWARD_N{i:04d}",
                "user_id": f"U{user_num:04d}",
                "teacher_id": teacher_by_course[course_id],
                "live_session_id": f"LIVE_{(i % 8) + 1:03d}",
                "reward_amount": Decimal(str((i % 5 + 1) * 10)).quantize(Decimal("0.01")),
                "device_id": f"DEV_NORMAL_{user_num:04d}",
                "guardian_consent_snapshot": "已同意" if user_num % 3 == 0 else "不适用",
                "payment_account_hash": stable_hash(f"pay-account:U{user_num:04d}"),
                "status": "已支付",
                "reward_time": anchor - timedelta(days=i % 30, minutes=i * 3),
            }
        )

    # 单场 6800 元、5 天新账号、监护同意待确认。
    tables["live_reward"].append(
        {
            "reward_id": "REWARD_RISK_0001",
            "user_id": "RISK_LIVE_001",
            "teacher_id": "T001",
            "live_session_id": "LIVE_RISK_001",
            "reward_amount": Decimal("6800.00"),
            "device_id": "DEV_RISK_LIVE_001",
            "guardian_consent_snapshot": "待确认",
            "payment_account_hash": stable_hash("pay-account:RISK_LIVE_001"),
            "status": "已拦截",
            "reward_time": anchor - timedelta(minutes=10),
        }
    )

    blacklist_values = (
        (1, "学号", "RB000006", "批量刷报名确认账号"),
        (2, "学号", "RR000003", "多次异常退费确认账号"),
        (3, "设备指纹", "DEV_RISK_BRUSH_SHARED", "批量注册和集中报名设备"),
        (4, "设备指纹", "DEV_RISK_PROXY_SHARED", "多个学员共用代理学习设备"),
        (5, "设备指纹", "DEV_RISK_LIVE_001", "未成年人异常高额消费设备"),
        (6, "直播账号", "LIVE_RISK_001", "异常打赏直播场次"),
        (7, "身份证哈希", stable_hash("demo-id-card:RISK_REFUND_003"), "连环退费身份"),
        (8, "身份证哈希", stable_hash("demo-id-card:RISK_BIG_001"), "短时大额连报身份"),
    )
    for entry_id, entry_type, entry_value, reason in blacklist_values:
        tables["blacklist_extra"].append(
            {
                "entry_id": entry_id,
                "entry_type": entry_type,
                "entry_value": entry_value,
                "reason": reason,
                "expire_at": None,
                "is_active": True,
                "create_time": anchor,
            }
        )

    return BusinessDataset(anchor=anchor, seed=seed, tables=tables)


def sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, datetime):
        return "'" + value.strftime("%Y-%m-%d %H:%M:%S") + "'"
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, int):
        return str(value)
    escaped = str(value).replace("\\", "\\\\").replace("'", "''")
    return f"'{escaped}'"


def chunks(rows: Sequence[dict[str, Any]], size: int = 100) -> Iterable[Sequence[dict[str, Any]]]:
    for start in range(0, len(rows), size):
        yield rows[start:start + size]


def render_insert(table: str, rows: Sequence[dict[str, Any]]) -> str:
    columns = TABLE_COLUMNS[table]
    quoted_columns = ", ".join(f"`{name}`" for name in columns)
    update_columns = [name for name in columns if name not in _primary_key_columns(table)]
    update_clause = ", ".join(
        f"`{name}`=new.`{name}`" for name in update_columns
    )

    statements = []
    for batch in chunks(rows):
        values = []
        for row in batch:
            missing = set(columns) - set(row)
            if missing:
                raise ValueError(f"{table} 行缺少字段: {sorted(missing)}")
            values.append(
                "(" + ", ".join(sql_literal(row[name]) for name in columns) + ")"
            )
        statements.append(
            f"INSERT INTO `{table}` ({quoted_columns}) VALUES\n  "
            + ",\n  ".join(values)
            + f"\nAS new\nON DUPLICATE KEY UPDATE {update_clause};"
        )
    return "\n\n".join(statements)


def _primary_key_columns(table: str) -> set[str]:
    return {
        "user_info": {"user_id"},
        "course": {"course_id"},
        "order_info": {"order_id"},
        "learning_progress": {"progress_id"},
        "refund_request": {"refund_id"},
        "live_reward": {"reward_id"},
        "blacklist_extra": {"entry_id"},
    }[table]


def render_sql(dataset: BusinessDataset) -> str:
    counts = dataset.counts()
    header = f"""-- ============================================================
-- 教育行业 AI 风控系统 - 业务样例数据
-- 由 scripts/gen_business_data.py 自动生成，请勿手工维护大批量数据
-- seed={dataset.seed}, anchor={dataset.anchor.isoformat(timespec='seconds')}
-- 总行数={dataset.total_rows}, 可作为事件来源的行数={dataset.event_rows}
-- user={counts['user_info']}, course={counts['course']}, order={counts['order_info']},
-- progress={counts['learning_progress']}, refund={counts['refund_request']},
-- reward={counts['live_reward']}, blacklist_extra={counts['blacklist_extra']}
-- ============================================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;
START TRANSACTION;
"""
    sections = [header.rstrip()]
    for table in TABLE_COLUMNS:
        sections.append(f"-- {table}\n{render_insert(table, dataset.tables[table])}")
    sections.append("COMMIT;\nSET FOREIGN_KEY_CHECKS = 1;")
    return "\n\n".join(sections) + "\n"


def parse_anchor(value: str | None) -> datetime:
    if value:
        return datetime.fromisoformat(value)
    return datetime.now().replace(microsecond=0)


def apply_sql(sql_text: str, args: argparse.Namespace) -> None:
    try:
        import pymysql
    except ImportError as exc:
        raise SystemExit("--apply 需要先安装 requirements.txt 中的 pymysql") from exc

    connection = pymysql.connect(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        database=args.db,
        charset="utf8mb4",
        autocommit=True,
    )
    try:
        statements = [part.strip() for part in sql_text.split(";") if part.strip()]
        with connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)
        print(f"已写入 MySQL: {args.user}@{args.host}:{args.port}/{args.db}")
    finally:
        connection.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="生成教育行业正常与风险业务数据")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="SQL 输出路径")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="随机种子")
    parser.add_argument(
        "--anchor", help="数据时间锚点，ISO 格式；不传则使用当前时间"
    )
    parser.add_argument("--apply", action="store_true", help="生成后写入 MySQL")
    parser.add_argument("--host", default=os.getenv("DB_HOST", "localhost"))
    parser.add_argument("--port", type=int, default=int(os.getenv("DB_PORT", "3306")))
    parser.add_argument("--user", default=os.getenv("DB_USER", "root"))
    parser.add_argument("--password", default=os.getenv("DB_PASSWORD", "123456"))
    parser.add_argument("--db", default=os.getenv("DB_NAME", "ecs"))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    dataset = build_dataset(parse_anchor(args.anchor), args.seed)
    sql_text = render_sql(dataset)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(sql_text, encoding="utf-8", newline="\n")

    print("教育业务数据生成完成")
    print(f"输出: {args.output.resolve()}")
    print(f"seed={dataset.seed}, anchor={dataset.anchor.isoformat(timespec='seconds')}")
    print(f"总行数={dataset.total_rows}, 事件来源行数={dataset.event_rows}")
    for table, count in dataset.counts().items():
        print(f"  {table:<22} {count:>4}")

    if args.apply:
        apply_sql(sql_text, args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
