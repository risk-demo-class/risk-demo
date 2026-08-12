"""银行信贷风控 - 业务表 DDL 同步检查 (RED 基线).

用 SQLAlchemy 反射 ecs 数据库, 断言 17 张银行业务表存在且字段对齐,
并断言电商表已移除. 需要真实数据库 (DB_PORT=3307).
"""
import pytest
from sqlalchemy import create_engine, inspect

# 17 张银行业务表 (T-01, CONTEXT.md 术语)
BANK_TABLES = [
    "customer_info", "region", "loan_product_category", "loan_status",
    "bank_branch", "repayment_status", "contact_info", "loan_product",
    "overdue_reason", "loan_application", "repayment_record",
    "loan_installment", "loan_repayment_rel", "complaint_content",
    "complaint_record", "overdue_record", "overdue_repayment_rel",
]

# 需移除的电商表 (全量替换)
ECOM_TABLES = [
    "user_info", "order_info", "order_detail", "sku_info",
    "receive_info", "postsale", "logistics", "logistics_complaint",
    "logistics_complaints_record",
]


def _inspect():
    from app.config import settings
    url = settings.get_database_url_async().replace("+aiomysql", "+pymysql")
    return inspect(create_engine(url))


def test_bank_tables_all_exist():
    insp = _inspect()
    missing = [t for t in BANK_TABLES if not insp.has_table(t)]
    assert not missing, f"缺少银行表: {missing}"


def test_ecom_tables_removed():
    insp = _inspect()
    leftover = [t for t in ECOM_TABLES if insp.has_table(t)]
    assert not leftover, f"电商表未移除: {leftover}"


def test_loan_application_fields():
    insp = _inspect()
    cols = {c["name"] for c in insp.get_columns("loan_application")}
    expected = {
        "loan_id", "apply_time", "approve_time", "loan_time",
        "mature_time", "customer_id", "contact_id", "loan_status",
        "loan_amount", "loan_term_month", "installment_count",
        "annual_income", "debt_amount", "device_id",
    }
    assert not (expected - cols), f"loan_application 缺字段: {expected - cols}"


def test_customer_info_fields():
    insp = _inspect()
    cols = {c["name"] for c in insp.get_columns("customer_info")}
    expected = {"customer_id", "customer_phone", "id_card_no", "status"}
    assert not (expected - cols), f"customer_info 缺字段: {expected - cols}"