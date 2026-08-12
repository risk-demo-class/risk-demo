"""
电信风控系统 - 业务表 ORM (13 张)
================================
映射 telecom 库的 13 张业务表 (客户/号卡/渠道/基站/设备/套餐/CDR/SMS/流量/业务办理等).
参照 ai_risk/app/models_business.py 风格:
  - SQLAlchemy 2.0 Mapped 风格
  - 无外键约束 (逻辑关联, 方便造数 + 风控 JOIN)
  - 中文 comment
  - 字段/索引与 sql/init_telecom_tables.sql 严格对齐

不参与风控决策本身, 但被特征工程 (engine/feature.py) 和规则引擎查询.
核心枢纽: telecom_card.msisdn (所有事实表通过号码关联).
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Enum,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


# ============================================================
# 基础域
# ============================================================

class TelecomRegion(Base):
    """地区表 (省/市/区 标准化)"""
    __tablename__ = "telecom_region"

    province: Mapped[str] = mapped_column(String(20), primary_key=True, comment="省")
    city: Mapped[str] = mapped_column(String(20), primary_key=True, comment="市")
    district: Mapped[str] = mapped_column(String(20), primary_key=True, comment="区/县")


class TelecomCustomer(Base):
    """客户实名信息表 (1客户 N号卡). id_no 支撑一证多卡查询 (反诈法第10条)"""
    __tablename__ = "telecom_customer"

    customer_id: Mapped[str] = mapped_column(String(20), primary_key=True, comment="客户ID (C+8位)")
    customer_type: Mapped[str] = mapped_column(
        Enum("个人", "企业", name="cust_type_enum"), nullable=False, default="个人", comment="客户类型",
    )
    id_type: Mapped[str] = mapped_column(
        Enum("身份证", "护照", "营业执照", name="id_type_enum"), nullable=False, default="身份证", comment="证件类型",
    )
    id_no: Mapped[str] = mapped_column(String(32), nullable=False, comment="证件号 (一证多卡查询键)")
    real_name: Mapped[str] = mapped_column(String(50), nullable=False, comment="实名姓名")
    gender: Mapped[str] = mapped_column(
        Enum("男", "女", "未知", name="gender_enum"), nullable=False, default="未知", comment="性别",
    )
    birthday: Mapped[Optional[date]] = mapped_column(Date, comment="出生日期")
    face_verify_status: Mapped[str] = mapped_column(
        Enum("通过", "未通过", "未核验", name="face_verify_enum"), nullable=False, default="未核验", comment="活体核验状态",
    )
    register_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="注册时间")
    risk_tag: Mapped[Optional[str]] = mapped_column(String(20), comment="风险标签 (正常/中风险/高风险/涉诈)")


class TelecomChannel(Base):
    """渠道/代理商表 (反诈法第9条代理商管理)"""
    __tablename__ = "telecom_channel"

    channel_id: Mapped[str] = mapped_column(String(20), primary_key=True, comment="渠道ID (CH+4位)")
    channel_name: Mapped[str] = mapped_column(String(80), nullable=False, comment="渠道名称")
    channel_type: Mapped[str] = mapped_column(
        Enum("营业厅", "代理商", "线上自助", name="channel_type_enum"), nullable=False, comment="渠道类型",
    )
    province: Mapped[str] = mapped_column(String(20), nullable=False, comment="渠道所在省")
    agent_id: Mapped[Optional[str]] = mapped_column(String(20), comment="代理商编号")
    status: Mapped[str] = mapped_column(
        Enum("正常", "停用", "整改中", name="channel_status_enum"), nullable=False, default="正常", comment="状态",
    )
    open_date: Mapped[date] = mapped_column(Date, nullable=False, comment="开通日期")


class TelecomCell(Base):
    """基站表 (CDR 定位用, 支撑机卡异地/GOIP 固定点位识别)"""
    __tablename__ = "telecom_cell"

    cell_id: Mapped[str] = mapped_column(String(20), primary_key=True, comment="基站标识 (CGI)")
    lac: Mapped[str] = mapped_column(String(10), nullable=False, comment="位置区码")
    province: Mapped[str] = mapped_column(String(20), nullable=False, comment="省")
    city: Mapped[str] = mapped_column(String(20), nullable=False, comment="市")
    district: Mapped[str] = mapped_column(String(20), nullable=False, comment="区/县")
    cell_type: Mapped[str] = mapped_column(
        Enum("宏站", "微站", "室内分布", name="cell_type_enum"), nullable=False, default="宏站", comment="基站类型",
    )
    longitude: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6), comment="经度")
    latitude: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6), comment="纬度")


class TelecomDevice(Base):
    """设备表 (IMEI + MAC 设备指纹, 支撑一机多卡/猫池/换卡检测)"""
    __tablename__ = "telecom_device"

    imei: Mapped[str] = mapped_column(String(15), primary_key=True, comment="设备IMEI (15位)")
    mac_address: Mapped[Optional[str]] = mapped_column(String(17), comment="设备MAC地址 (XX:XX:XX:XX:XX:XX)")
    brand: Mapped[str] = mapped_column(String(30), nullable=False, comment="品牌")
    model: Mapped[str] = mapped_column(String(60), nullable=False, comment="型号")
    os_type: Mapped[str] = mapped_column(
        Enum("Android", "iOS", "HarmonyOS", "其他", name="os_type_enum"), nullable=False, default="其他", comment="操作系统",
    )
    first_seen_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="首次出现时间")


class TelecomPlan(Base):
    """套餐表"""
    __tablename__ = "telecom_plan"

    plan_id: Mapped[str] = mapped_column(String(20), primary_key=True, comment="套餐ID")
    plan_name: Mapped[str] = mapped_column(String(60), nullable=False, comment="套餐名称")
    plan_type: Mapped[str] = mapped_column(
        Enum("语音套餐", "流量套餐", "融合套餐", "物联网套餐", name="plan_type_enum"), nullable=False, comment="套餐类型",
    )
    monthly_fee: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False, comment="月费(元)")
    data_quota_mb: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="流量配额(MB)")
    voice_quota_min: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="语音配额(分钟)")
    sms_quota: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="短信配额(条)")


# ============================================================
# 号卡域 (核心)
# ============================================================

class TelecomCard(Base):
    """号卡表 (核心枢纽). 1客户N卡, 1渠道N卡, 1设备N卡.

    风控索引: customer_id(一证多卡) / current_imei(一机多卡) /
    open_channel_id(渠道异常) / open_time / card_status / is_iot
    """
    __tablename__ = "telecom_card"

    msisdn: Mapped[str] = mapped_column(String(11), primary_key=True, comment="手机号 (MSISDN, 11位)")
    imsi: Mapped[str] = mapped_column(String(15), nullable=False, unique=True, comment="SIM 卡 IMSI")
    iccid: Mapped[str] = mapped_column(String(20), nullable=False, unique=True, comment="SIM 序列号 ICCID")
    customer_id: Mapped[str] = mapped_column(String(20), nullable=False, comment="客户ID (逻辑关联 telecom_customer)")
    current_imei: Mapped[Optional[str]] = mapped_column(String(15), comment="当前绑定设备 IMEI")
    plan_id: Mapped[str] = mapped_column(String(20), nullable=False, comment="套餐ID")
    open_channel_id: Mapped[str] = mapped_column(String(20), nullable=False, comment="开卡渠道ID")
    open_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="开卡时间")
    open_province: Mapped[str] = mapped_column(String(20), nullable=False, comment="开卡省")
    card_status: Mapped[str] = mapped_column(
        Enum("正常", "停机", "暂停", "已销户", name="card_status_enum"), nullable=False, default="正常", comment="号卡状态",
    )
    roam_status: Mapped[str] = mapped_column(
        Enum("归属地", "省内漫游", "省间漫游", "国际漫游", name="roam_status_enum"),
        nullable=False, default="归属地", comment="漫游状态",
    )
    intl_call_enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="国际来去电是否开通 (0否1是)")
    is_iot: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="是否物联网卡 (0否1是)")
    status_update_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="状态更新时间")


class TelecomIotCard(Base):
    """物联网卡扩展表 (1:1 对应 is_iot=1 的号卡, 反诈法第12条)"""
    __tablename__ = "telecom_iot_card"

    msisdn: Mapped[str] = mapped_column(String(11), primary_key=True, comment="号卡 (关联 telecom_card)")
    iot_scene: Mapped[str] = mapped_column(String(30), nullable=False, comment="应用场景 (车联网/智能表计/POS/工业/其他)")
    bound_device_imei: Mapped[Optional[str]] = mapped_column(String(15), comment="绑定设备 IMEI")
    device_type: Mapped[str] = mapped_column(String(40), nullable=False, comment="设备类型")
    function_scope: Mapped[str] = mapped_column(
        Enum("仅数据", "仅短信", "语音+数据", "语音+数据+短信", name="iot_func_enum"),
        nullable=False, default="仅数据", comment="限定功能",
    )
    activate_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="激活时间")


class TelecomCardDeviceBinding(Base):
    """机卡绑定历史表 (号卡换设备全历史, 支撑一机多卡/频繁换机)"""
    __tablename__ = "telecom_card_device_binding"

    bind_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="绑定记录ID")
    msisdn: Mapped[str] = mapped_column(String(11), nullable=False, comment="号卡")
    imei: Mapped[str] = mapped_column(String(15), nullable=False, comment="设备IMEI")
    bind_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="绑定时间")
    unbind_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="解绑时间 (NULL=当前绑定中)")
    bind_province: Mapped[str] = mapped_column(String(20), nullable=False, comment="绑定时的省")


# ============================================================
# 通信行为域 (事实表, 大表)
# ============================================================

class TelecomCdr(Base):
    """通话记录表 CDR (核心事实表).

    风控索引面向特征计算:
      (calling_no, start_time) -> 某号近N分钟主叫次数 (短时高频)
      (cell_id, start_time) -> 固定点位通信负荷 (GOIP识别)
      (roam_type, start_time) -> 国际来电识别
    """
    __tablename__ = "telecom_cdr"

    cdr_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="CDR ID")
    calling_no: Mapped[str] = mapped_column(String(11), nullable=False, comment="主叫号码")
    called_no: Mapped[str] = mapped_column(String(20), nullable=False, comment="被叫号码 (可固话/国际号)")
    call_type: Mapped[str] = mapped_column(
        Enum("主叫", "被叫", "呼转", name="call_type_enum"), nullable=False, default="主叫", comment="通话类型",
    )
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="通话开始时间")
    end_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="通话结束时间")
    duration: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="通话时长(秒)")
    cell_id: Mapped[str] = mapped_column(String(20), nullable=False, comment="通话基站")
    imei: Mapped[Optional[str]] = mapped_column(String(15), comment="通话时设备IMEI")
    roam_type: Mapped[str] = mapped_column(
        Enum("本地", "省内漫游", "省间漫游", "国际", name="cdr_roam_enum"), nullable=False, default="本地", comment="漫游类型",
    )
    call_from_country: Mapped[Optional[str]] = mapped_column(String(40), comment="国际来电归属国家 (国际来电填)")


class TelecomSms(Base):
    """短信记录表 (支撑短时高频短信/群发诈骗识别)"""
    __tablename__ = "telecom_sms"

    sms_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="短信ID")
    sending_no: Mapped[str] = mapped_column(String(11), nullable=False, comment="发送方号码")
    receiving_no: Mapped[str] = mapped_column(String(20), nullable=False, comment="接收方号码")
    send_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="发送时间")
    sms_type: Mapped[str] = mapped_column(
        Enum("普通短信", "端口短信", "国际短信", name="sms_type_enum"), nullable=False, default="普通短信", comment="短信类型",
    )
    cell_id: Mapped[Optional[str]] = mapped_column(String(20), comment="基站")
    imei: Mapped[Optional[str]] = mapped_column(String(15), comment="设备IMEI")


class TelecomDataUsage(Base):
    """流量使用表 (按天聚合, 支撑流量突增/物联网卡滥用识别)"""
    __tablename__ = "telecom_data_usage"

    usage_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="记录ID")
    msisdn: Mapped[str] = mapped_column(String(11), nullable=False, comment="号卡")
    usage_date: Mapped[date] = mapped_column(Date, nullable=False, comment="使用日期")
    data_volume_mb: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="当日流量(MB)")
    cell_id: Mapped[Optional[str]] = mapped_column(String(20), comment="主要基站")
    roam_type: Mapped[str] = mapped_column(
        Enum("本地", "省内漫游", "省间漫游", "国际", name="usage_roam_enum"), nullable=False, default="本地", comment="漫游类型",
    )


# ============================================================
# 业务办理域
# ============================================================

class TelecomServiceOrder(Base):
    """业务办理记录表 (开户/补卡/销户/套餐变更/解除限制 等).

    风控索引:
      (channel_id, order_time) -> 渠道开卡量异常 (反诈法第10条异常办卡)
      (customer_id, order_time) -> 一证频繁补卡销户
    """
    __tablename__ = "telecom_service_order"

    order_id: Mapped[str] = mapped_column(String(30), primary_key=True, comment="业务单号 (SO+时间戳)")
    msisdn: Mapped[str] = mapped_column(String(11), nullable=False, comment="号卡")
    customer_id: Mapped[str] = mapped_column(String(20), nullable=False, comment="客户ID")
    channel_id: Mapped[str] = mapped_column(String(20), nullable=False, comment="办理渠道")
    order_type: Mapped[str] = mapped_column(
        Enum("新开户", "补卡", "换卡", "过户", "销户", "套餐变更", "停复机", "解除限制", "实名核验",
             name="order_type_enum"),
        nullable=False, comment="业务类型",
    )
    order_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="办理时间")
    order_province: Mapped[str] = mapped_column(String(20), nullable=False, comment="办理省")
    order_status: Mapped[str] = mapped_column(
        Enum("成功", "失败", "审核中", name="order_status_enum"), nullable=False, default="成功", comment="办理状态",
    )
    face_verify_result: Mapped[str] = mapped_column(
        Enum("通过", "未通过", "未核验", name="order_face_enum"), nullable=False, default="未核验", comment="活体核验结果",
    )
    remark: Mapped[Optional[str]] = mapped_column(String(200), comment="备注")


# ============================================================
# 账单域
# ============================================================

class TelecomBillingRecord(Base):
    """话费账单表 (充值/消费/转出 → 话费套现识别, 反诈法第14条)"""
    __tablename__ = "telecom_billing_record"

    record_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="账单记录ID")
    msisdn: Mapped[str] = mapped_column(String(11), nullable=False, comment="号卡")
    bill_month: Mapped[str] = mapped_column(String(7), nullable=False, comment="账期 (YYYY-MM)")
    bill_type: Mapped[str] = mapped_column(
        Enum("充值", "消费", "转出", "退款", "调账", name="billing_type_enum"),
        nullable=False, comment="账单类型",
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, comment="金额(元)")
    balance_before: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), comment="变动前余额")
    balance_after: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), comment="变动后余额")
    pay_channel: Mapped[Optional[str]] = mapped_column(String(20), comment="支付渠道")
    remark: Mapped[Optional[str]] = mapped_column(String(200), comment="备注")
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="发生时间")


# ============================================================
# 集团客户域
# ============================================================

class TelecomGroupCustomer(Base):
    """集团客户表 (政企/校园/商户 → 子号异常识别)"""
    __tablename__ = "telecom_group_customer"

    group_id: Mapped[str] = mapped_column(String(20), primary_key=True, comment="集团ID (G+8位)")
    group_name: Mapped[str] = mapped_column(String(80), nullable=False, comment="集团名称")
    group_type: Mapped[str] = mapped_column(
        Enum("政企", "校园", "商户", "其他", name="group_type_enum"),
        nullable=False, default="政企", comment="集团类型",
    )
    customer_id: Mapped[str] = mapped_column(String(20), nullable=False, comment="关联主客户ID")
    contact_person: Mapped[Optional[str]] = mapped_column(String(50), comment="联系人")
    contact_phone: Mapped[Optional[str]] = mapped_column(String(20), comment="联系电话")
    open_date: Mapped[date] = mapped_column(Date, nullable=False, comment="开户日期")
    group_status: Mapped[str] = mapped_column(
        Enum("正常", "冻结", "销户", name="group_status_enum"),
        nullable=False, default="正常", comment="集团状态",
    )
