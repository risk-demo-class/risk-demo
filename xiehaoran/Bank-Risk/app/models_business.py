"""
银行风控系统 - 核心业务表 ORM 模型 (SQLAlchemy 2.x)

本文件是 Bank-Risk 项目的「必须自建」模块 (对应业务说明文档「模块边界对齐」):
  - 银行核心业务表 / 银行特征工程 / 银行 event_type 枚举 / 监管合规约束 均不可复用基线 AI_Risk
  - 复用基线: Base.metadata / decorators.print_execution_time / 决策流水线框架

6 张核心表 (均带 `_biz` 前缀避免与基线电商业务表冲突):
  1. merchant_info       商户信息表   (收单/对公账户主体)
  2. txn_flow            交易流水表   (转账/卡片/还款, 风控特征主数据源)
  3. settlement_log      结算记录表   (T+1 清算/差错/调单)
  4. user_behavior_log   用户行为日志表 (登录/改绑/交易前置行为)
  5. risk_event_biz      风险事件表   (一票否决 / 可疑交易 / 反诈止付, 关联风控流水线)
  6. relation_graph      关联关系表   (资金归集/同设备/IP/同受益人, 团伙识别)

字段设计预留风控特征扩展空间:
  - 每张表含 `f_ext_*` 保留字段 (JSON/文本) 供 feature.py 动态落特征
  - 交易流水表按 (merchant_id, txn_time) 分区 (MySQL 原生 PARTITION BY RANGE)
  - 统一 `created_at / updated_at` 审计字段; 金额统一 19,4 (DECIMAL) 规避浮点误差
"""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import declarative_base, relationship

from app.database import Base
from app.decorators import print_execution_time


# ============================================================
# 1. 商户信息表 merchant_info  (收单/对公账户主体)
# ============================================================
class MerchantInfo(Base):
    __tablename__ = "merchant_info"
    __comment__ = "商户信息表(收单/对公账户主体)"

    merchant_id = Column(String(32), primary_key=True, comment="商户/对公账户编号 PK")
    merchant_name = Column(String(128), nullable=False, comment="商户名称/企业名称")
    merchant_type = Column(
        String(16), nullable=False,
        comment="商户类型: 个体/企业/对公通道/个人收款码",
    )
    mcc_code = Column(String(8), nullable=True, comment="商户类别码 MCC")
    legal_person = Column(String(64), nullable=True, comment="法人/实际控制人")
    id_card_no = Column(String(32), nullable=True, comment="法人证件号(脱敏存储)")
    contact_phone = Column(String(20), nullable=True, comment="预留手机号(脱敏)")
    province = Column(String(32), nullable=True, comment="注册省份")
    city = Column(String(32), nullable=True, comment="注册城市")
    risk_level = Column(
        SmallInteger, nullable=False, default=0,
        comment="商户风险等级 0低 1中 2高 (贷前/巡检结果)",
    )
    status = Column(
        SmallInteger, nullable=False, default=1,
        comment="状态 1正常 2冻结 3注销 4涉案冻结",
    )
    open_date = Column(DateTime, nullable=True, comment="入网/开户日期")
    f_ext_json = Column(
        JSON, nullable=True,
        comment="风控特征扩展位(经营类目/月均流水/涉案标记等)",
    )
    created_at = Column(DateTime, nullable=False, server_default=func.now(), comment="创建时间")
    updated_at = Column(
        DateTime, nullable=False, server_default=func.now(),
        onupdate=func.now(), comment="更新时间",
    )

    # 关系: 一个商户 N 笔交易 / N 条结算
    txns = relationship(
        "TxnFlow", back_populates="merchant",
        cascade="save-update, merge", passive_deletes=False,
    )
    settlements = relationship(
        "SettlementLog", back_populates="merchant",
        cascade="save-update, merge", passive_deletes=False,
    )

    __table_args__ = (
        Index("ix_merchant_name", "merchant_name"),
        Index("ix_merchant_type_status", "merchant_type", "status"),
        Index("ix_merchant_risk", "risk_level"),
        UniqueConstraint("id_card_no", name="uq_merchant_idcard"),
    )


# ============================================================
# 2. 交易流水表 txn_flow  (风控特征主数据源, 按时间分区)
# ============================================================
class TxnFlow(Base):
    __tablename__ = "txn_flow"
    __comment__ = "交易流水表(转账/卡片/还款, 风控特征主数据源)"

    txn_id = Column(String(40), primary_key=True, comment="交易流水号 PK (全局唯一)")
    merchant_id = Column(
        String(32), nullable=True,
        comment="商户/对公账户编号 (分区表不支持FK, 一致性由应用层保证)",
    )
    cust_id = Column(String(32), nullable=False, comment="客户/付款人编号")
    counterparty_id = Column(String(32), nullable=True, comment="交易对手/收款人编号")
    counterparty_account = Column(String(40), nullable=True, comment="收款账号(脱敏)")
    txn_type = Column(
        String(16), nullable=False,
        comment="交易类型: transfer/loan_apply/card_txn/repay/login",
    )
    channel = Column(String(16), nullable=True, comment="渠道: 手机银行/网银/ATM/POS/柜面")
    amount = Column(Numeric(19, 4), nullable=False, comment="交易金额(元)")
    currency = Column(String(3), nullable=False, default="CNY", comment="币种")
    txn_time = Column(DateTime, nullable=False, comment="交易时间(分区键)")
    device_fingerprint = Column(String(64), nullable=True, comment="设备指纹")
    ip_addr = Column(String(45), nullable=True, comment="客户端 IP")
    geo_province = Column(String(32), nullable=True, comment="交易地理-省")
    geo_city = Column(String(32), nullable=True, comment="交易地理-市")
    txn_status = Column(
        SmallInteger, nullable=False, default=1,
        comment="1成功 2失败 3可疑拦截 4保护性止付 5已报送",
    )
    is_fraud = Column(Boolean, nullable=False, default=False, comment="是否确认为欺诈/涉案")
    f_speed = Column(Numeric(10, 2), nullable=True, comment="特征: 快进快出耗时(分钟)")
    f_counterparty_cnt = Column(Integer, nullable=True, comment="特征: 近1h交易对手数")
    f_ext_json = Column(JSON, nullable=True, comment="风控特征扩展位")
    created_at = Column(DateTime, nullable=False, server_default=func.now(), comment="创建时间")

    merchant = relationship("MerchantInfo", back_populates="txns")
    # 一笔交易 -> 多条结算 (一对多, 结算可能分批)
    settlements = relationship(
        "SettlementLog", back_populates="txn",
        cascade="all, delete-orphan", passive_deletes=True,
    )
    # 一笔交易 -> 可触发多条风险事件
    risk_events = relationship(
        "RiskEventBiz", back_populates="txn",
        cascade="all, delete-orphan", passive_deletes=True,
    )

    __table_args__ = (
        Index("ix_txn_merchant_time", "merchant_id", "txn_time"),
        Index("ix_txn_cust_time", "cust_id", "txn_time"),
        Index("ix_txn_counterparty", "counterparty_id"),
        Index("ix_txn_type_status", "txn_type", "txn_status"),
        Index("ix_txn_device", "device_fingerprint"),
        Index("ix_txn_fraud", "is_fraud", "txn_time"),
        CheckConstraint("amount >= 0", name="ck_txn_amount_nonneg"),
    )


# ============================================================
# 3. 结算记录表 settlement_log  (T+1 清算/差错/调单)
# ============================================================
class SettlementLog(Base):
    __tablename__ = "settlement_log"
    __comment__ = "结算记录表(T+1清算/差错/调单)"

    settle_id = Column(String(40), primary_key=True, comment="结算流水号 PK")
    txn_id = Column(
        String(40), nullable=False,
        comment="关联交易流水号 (分区表不支持FK, 一致性由应用层保证)",
    )
    merchant_id = Column(
        String(32), nullable=True,
        comment="关联商户编号 (分区表不支持FK, 一致性由应用层保证)",
    )
    settle_amount = Column(Numeric(19, 4), nullable=False, comment="结算金额(元)")
    fee_amount = Column(Numeric(19, 4), nullable=False, default=0, comment="手续费")
    net_amount = Column(Numeric(19, 4), nullable=False, comment="净额=结算-手续费")
    settle_date = Column(DateTime, nullable=False, comment="清算日期(分区键)")
    settle_status = Column(
        SmallInteger, nullable=False, default=1,
        comment="1待清算 2已清算 3差错 4调单 5退回",
    )
    error_code = Column(String(16), nullable=True, comment="差错码(如调单/退货)")
    f_ext_json = Column(JSON, nullable=True, comment="风控特征扩展位")
    created_at = Column(DateTime, nullable=False, server_default=func.now(), comment="创建时间")

    txn = relationship("TxnFlow", back_populates="settlements")
    merchant = relationship("MerchantInfo", back_populates="settlements")

    __table_args__ = (
        Index("ix_settle_txn", "txn_id"),
        Index("ix_settle_merchant_date", "merchant_id", "settle_date"),
        Index("ix_settle_status", "settle_status"),
        CheckConstraint("settle_amount >= 0", name="ck_settle_amount_nonneg"),
        CheckConstraint("net_amount >= 0", name="ck_settle_net_nonneg"),
    )


# ============================================================
# 4. 用户行为日志表 user_behavior_log  (登录/改绑/交易前置行为)
# ============================================================
class UserBehaviorLog(Base):
    __tablename__ = "user_behavior_log"
    __comment__ = "用户行为日志表(登录/改绑/交易前置行为)"

    log_id = Column(BigInteger, primary_key=True, autoincrement=True, comment="行为日志自增ID PK")
    cust_id = Column(String(32), nullable=False, comment="客户编号")
    action = Column(
        String(24), nullable=False,
        comment="行为: login/login_fail/change_bind/transfer_prepay/query",
    )
    action_time = Column(DateTime, nullable=False, comment="行为时间(分区键)")
    device_fingerprint = Column(String(64), nullable=True, comment="设备指纹")
    ip_addr = Column(String(45), nullable=True, comment="IP")
    geo_province = Column(String(32), nullable=True, comment="地理-省")
    geo_city = Column(String(32), nullable=True, comment="地理-市")
    result = Column(SmallInteger, nullable=False, default=1, comment="1成功 0失败")
    f_ext_json = Column(JSON, nullable=True, comment="风控特征扩展位(会话/UA等)")
    created_at = Column(DateTime, nullable=False, server_default=func.now(), comment="创建时间")

    __table_args__ = (
        Index("ix_behavior_cust_time", "cust_id", "action_time"),
        Index("ix_behavior_action", "action"),
        Index("ix_behavior_device", "device_fingerprint"),
    )


# ============================================================
# 5. 风险事件表 risk_event_biz  (一票否决/可疑交易/反诈止付)
# ============================================================
class RiskEventBiz(Base):
    __tablename__ = "risk_event_biz"
    __comment__ = "风险事件表(一票否决/可疑交易/反诈止付)"

    event_id = Column(String(40), primary_key=True, comment="风险事件编号 PK")
    txn_id = Column(
        String(40), nullable=True,
        comment="关联交易流水号 (父表为分区表, 不支持FK, 一致性由应用层保证)",
    )
    cust_id = Column(String(32), nullable=True, comment="关联客户编号")
    event_type = Column(
        String(24), nullable=False,
        comment="事件类型: aml_suspect/veto/anti_fraud_freeze/blacklist_hit",
    )
    trigger_rule = Column(String(64), nullable=True, comment="触发规则/模型名")
    severity = Column(
        SmallInteger, nullable=False, default=1,
        comment="严重度 1低 2中 3高 4一票否决",
    )
    decision = Column(
        String(16), nullable=False,
        comment="决策: pass/review/reject/freeze/report",
    )
    reported = Column(Boolean, nullable=False, default=False, comment="是否已报送监管(AML/反诈)")
    report_no = Column(String(40), nullable=True, comment="报送流水号(大额/可疑交易报告)")
    detail_json = Column(JSON, nullable=True, comment="事件详情(命中特征/对手链)")
    created_at = Column(DateTime, nullable=False, server_default=func.now(), comment="创建时间")

    txn = relationship("TxnFlow", back_populates="risk_events")

    __table_args__ = (
        Index("ix_revent_txn", "txn_id"),
        Index("ix_revent_cust", "cust_id"),
        Index("ix_revent_type_sev", "event_type", "severity"),
        Index("ix_revent_reported", "reported"),
    )


# ============================================================
# 6. 关联关系表 relation_graph  (资金归集/同设备/IP/受益人, 团伙识别)
# ============================================================
class RelationGraph(Base):
    __tablename__ = "relation_graph"
    __comment__ = "关联关系表(资金归集/同设备/IP/受益人, 团伙识别)"

    relation_id = Column(BigInteger, primary_key=True, autoincrement=True, comment="关系自增ID PK")
    src_id = Column(String(40), nullable=False, comment="源节点(客户/商户/账户)")
    dst_id = Column(String(40), nullable=False, comment="目标节点(客户/商户/账户)")
    rel_type = Column(
        String(24), nullable=False,
        comment="关系: fund_collect/device_share/ip_share/beneficiary/same_phone",
    )
    weight = Column(Numeric(10, 4), nullable=False, default=1.0, comment="关系强度(出现频次)")
    first_seen = Column(DateTime, nullable=True, comment="首次发现时间")
    last_seen = Column(DateTime, nullable=True, comment="末次发现时间")
    is_suspicious = Column(Boolean, nullable=False, default=False, comment="是否可疑团伙边")
    f_ext_json = Column(JSON, nullable=True, comment="风控特征扩展位")
    created_at = Column(DateTime, nullable=False, server_default=func.now(), comment="创建时间")

    __table_args__ = (
        Index("ix_rel_src", "src_id"),
        Index("ix_rel_dst", "dst_id"),
        Index("ix_rel_type", "rel_type"),
        Index("ix_rel_susp", "is_suspicious"),
        UniqueConstraint("src_id", "dst_id", "rel_type", name="uq_relation_edge"),
    )


__all__ = [
    "MerchantInfo", "TxnFlow", "SettlementLog",
    "UserBehaviorLog", "RiskEventBiz", "RelationGraph",
]
