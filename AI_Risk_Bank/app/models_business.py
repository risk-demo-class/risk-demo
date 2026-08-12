"""
电商风控系统 - 业务表 ORM (17 张)
只读映射现有业务系统的核心实体 (用户/订单/物流/售后/收货等)
不参与风控决策本身, 但被特征工程和规则引擎查询
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


# ============================================================
# 用户与商品基础
# ============================================================

class UserInfo(Base):
    """用户信息表"""
    __tablename__ = "user_info"

    user_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="用户ID")


class Region(Base):
    """地区表 """
    __tablename__ = "region"

    province: Mapped[str] = mapped_column(String(20), primary_key=True, comment="省")
    city: Mapped[str] = mapped_column(String(20), primary_key=True, comment="市")
    district: Mapped[str] = mapped_column(String(20), primary_key=True, comment="区")


class ProductCategory(Base):
    """商品分类表"""
    __tablename__ = "product_category"

    product_category: Mapped[str] = mapped_column(String(20), primary_key=True, comment="商品类别")


class SkuInfo(Base):
    """商品信息表"""
    __tablename__ = "sku_info"

    sku_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="商品ID")
    sku_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="商品名称")
    sku_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, comment="商品价格")
    sku_category: Mapped[str] = mapped_column(String(20), nullable=False, comment="商品类别")
    sku_count: Mapped[int] = mapped_column(Integer, nullable=False, comment="商品数量")


# ============================================================
# 订单域
# ============================================================

class OrderStatus(Base):
    """订单状态表"""
    __tablename__ = "order_status"

    order_status: Mapped[str] = mapped_column(String(20), primary_key=True, comment="订单状态")
    status_code: Mapped[Optional[int]] = mapped_column(Integer, comment="状态码")


class OrderInfo(Base):
    """订单表"""
    __tablename__ = "order_info"

    order_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="订单ID")
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="创建时间")
    payment_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="支付时间")
    delivered_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="签收时间")
    complete_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="完成时间")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    receive_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="收货信息ID")
    order_status: Mapped[str] = mapped_column(String(20), nullable=False, comment="订单状态")


class OrderDetail(Base):
    """订单详细表"""
    __tablename__ = "order_detail"

    order_detail_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="订单详细ID")
    order_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="订单ID")
    sku_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="商品ID")
    sku_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="商品名称")
    sku_count: Mapped[int] = mapped_column(Integer, nullable=False, comment="商品数量")
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, comment="总单价格")
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, comment="折扣金额")
    final_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, comment="实付金额")


# ============================================================
# 物流域
# ============================================================

class Logistics(Base):
    """物流表"""
    __tablename__ = "logistics"

    logistics_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="物流ID")
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="创建时间")
    delivered_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="签收时间")
    logistics_tracking: Mapped[Optional[str]] = mapped_column(String(500), comment="物流详细")
    logistics_category: Mapped[Optional[str]] = mapped_column(
        Enum("自提", "物流中转", "专业配送", name="logistics_category_enum"),
        comment="物流类别",
    )


class OrderLogistics(Base):
    """订单物流关联关系表 """
    __tablename__ = "order_logistics"

    order_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="订单ID")
    logistics_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="物流ID")


class LogisticsCompany(Base):
    """物流公司表"""
    __tablename__ = "logistics_company"

    company_name: Mapped[str] = mapped_column(String(20), primary_key=True, comment="物流公司名称")


class LogisticsComplaint(Base):
    """物流投诉问题数据对应表 """
    __tablename__ = "logistics_complaint"

    logistics_status: Mapped[str] = mapped_column(String(20), primary_key=True, comment="物流状态")
    logistics_complaint: Mapped[str] = mapped_column(String(100), primary_key=True, comment="物流投诉问题")


class LogisticsComplaintsRecord(Base):
    """物流投诉记录表"""
    __tablename__ = "logistics_complaints_record"

    record_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="投诉记录ID")
    logistics_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="物流ID")
    logistics_complaint: Mapped[str] = mapped_column(String(500), nullable=False, comment="物流投诉问题")
    complaint_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="投诉时间")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")


# ============================================================
# 售后域
# ============================================================

class PostsaleStatus(Base):
    """售后状态表"""
    __tablename__ = "postsale_status"

    postsale_status: Mapped[str] = mapped_column(String(20), primary_key=True, comment="售后状态")
    is_refund: Mapped[int] = mapped_column(Integer, nullable=False, comment="是否退款")
    is_return: Mapped[int] = mapped_column(Integer, nullable=False, comment="是否退货")
    is_exchange: Mapped[int] = mapped_column(Integer, nullable=False, comment="是否换货")
    status_code: Mapped[Optional[int]] = mapped_column(Integer, comment="状态码")


class PostsaleReason(Base):
    """售后原因表"""
    __tablename__ = "postsale_reason"

    postsale_reason: Mapped[str] = mapped_column(String(100), primary_key=True, comment="售后原因")
    product_category: Mapped[Optional[str]] = mapped_column(String(20), comment="商品类别")


class Postsale(Base):
    """售后表"""
    __tablename__ = "postsale"

    postsale_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="售后ID")
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="创建时间")
    complete_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="完成时间")
    order_detail_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="订单详细ID")
    refund_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, comment="退款金额")
    postsale_type: Mapped[Optional[str]] = mapped_column(
        Enum("退款", "退货", "换货", name="postsale_type_enum"),
        comment="售后类型",
    )
    postsale_reason: Mapped[str] = mapped_column(String(500), nullable=False, comment="售后原因")
    postsale_status: Mapped[str] = mapped_column(String(20), nullable=False, comment="售后状态")
    receive_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="收货信息ID")


class PostsaleLogistics(Base):
    """售后物流关联关系表 """
    __tablename__ = "postsale_logistics"

    postsale_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="售后ID")
    logistics_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="物流ID")


# ============================================================
# 收货域
# ============================================================

class ReceiveInfo(Base):
    """收货信息表"""
    __tablename__ = "receive_info"

    receive_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="收货信息ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    receiver_name: Mapped[str] = mapped_column(String(50), nullable=False, comment="收货人姓名")
    receiver_phone: Mapped[str] = mapped_column(String(50), nullable=False, comment="收货人手机")
    receive_province: Mapped[str] = mapped_column(String(50), nullable=False, comment="收货省")
    receive_city: Mapped[str] = mapped_column(String(50), nullable=False, comment="收货市")
    receive_district: Mapped[str] = mapped_column(String(50), nullable=False, comment="收货区")
    receive_street_address: Mapped[str] = mapped_column(String(50), nullable=False, comment="收货详细地址")

# ============================================================
# 银行业务域（Bank edition）
# ============================================================

class BankUserInfo(Base):
    __tablename__ = "bank_user_info"
    user_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    id_card_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    credit_score: Mapped[int] = mapped_column(Integer, default=600)
    register_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    kyc_level: Mapped[str] = mapped_column(String(20), default="标准")
    account_status: Mapped[str] = mapped_column(String(20), default="正常")
    usual_city: Mapped[str] = mapped_column(String(50), default="上海")


class BankCard(Base):
    __tablename__ = "bank_card"
    card_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    card_no_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    bank_code: Mapped[str] = mapped_column(String(20), nullable=False)
    card_type: Mapped[str] = mapped_column(String(20), default="借记卡")
    credit_limit: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    card_status: Mapped[str] = mapped_column(String(20), default="正常")
    open_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class BankTransaction(Base):
    __tablename__ = "bank_transaction"
    txn_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    from_card: Mapped[str] = mapped_column(String(50), nullable=False)
    to_card: Mapped[str] = mapped_column(String(50), nullable=False)
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), default="手机银行")
    device_id: Mapped[str] = mapped_column(String(80), nullable=False)
    ip: Mapped[str] = mapped_column(String(64), nullable=False)
    geo: Mapped[str] = mapped_column(String(80), nullable=False)
    txn_status: Mapped[str] = mapped_column(String(20), default="成功")
    txn_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)


class LoanApplication(Base):
    __tablename__ = "loan_application"
    loan_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    term_months: Mapped[int] = mapped_column(Integer, nullable=False)
    purpose: Mapped[str] = mapped_column(String(100), nullable=False)
    monthly_income: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    debt_ratio: Mapped[float] = mapped_column(Numeric(6, 4), default=0)
    application_channel: Mapped[str] = mapped_column(String(20), default="APP")
    application_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    application_status: Mapped[str] = mapped_column(String(20), default="申请中")


class LoginLog(Base):
    __tablename__ = "login_log"
    login_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(String(80), nullable=False)
    ip: Mapped[str] = mapped_column(String(64), nullable=False)
    geo: Mapped[str] = mapped_column(String(80), nullable=False)
    success: Mapped[int] = mapped_column(Integer, default=1)
    login_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    login_channel: Mapped[str] = mapped_column(String(20), default="APP")


class DeviceFingerprint(Base):
    __tablename__ = "device_fingerprint"
    fingerprint_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    fingerprint_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    first_seen: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    os: Mapped[str] = mapped_column(String(40), default="Android")
    browser: Mapped[str] = mapped_column(String(40), default="AppWebView")
    is_emulator: Mapped[int] = mapped_column(Integer, default=0)


class IpGeoLocation(Base):
    __tablename__ = "ip_geo_location"
    ip: Mapped[str] = mapped_column(String(64), primary_key=True)
    country: Mapped[str] = mapped_column(String(40), default="中国")
    province: Mapped[str] = mapped_column(String(40), nullable=False)
    city: Mapped[str] = mapped_column(String(40), nullable=False)
    isp: Mapped[str] = mapped_column(String(80), default="运营商")
    is_proxy: Mapped[int] = mapped_column(Integer, default=0)
    is_tor: Mapped[int] = mapped_column(Integer, default=0)


class BankBlacklistExtra(Base):
    __tablename__ = "bank_blacklist_extra"
    entry_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    blacklist_type: Mapped[str] = mapped_column(String(20), nullable=False)
    blacklist_value: Mapped[str] = mapped_column(String(200), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(500))
    expire_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


