"""
银行风控系统 - 风控表 ORM (9 张)

保留基线 AI_Risk 风控表的全部结构 (规则/事件/特征/评估/案件/黑名单/画像/审计/告警),
但语义替换为银行域:
  - event_type 取值: transfer/loan_apply/card_txn/repay/login
  - rule_category 取值: 账户风险/交易风险/信贷风险/反洗钱/设备风险/登录风险
  - blacklist_type 取值: account/device/ip/phone/id_card/merchant/beneficiary
  - decision 取值: pass/review/reject/freeze/report (银行 5 级)
  - 不移植基线 17 张电商业务表 (订单/物流/售后/收货), 银行场景事件本身即风控对象
"""
import json
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


# ============================================================
# 规则配置
# ============================================================
class RiskRule(Base):
    __tablename__ = "risk_rule"

    rule_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="规则ID")
    rule_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="规则名称")
    rule_category: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="风险场景分类(银行域)",
    )
    event_type: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default="通用", comment="适用事件类型",
    )
    rule_condition: Mapped[str] = mapped_column(Text, nullable=False, comment="条件表达式(JSON)")
    risk_level: Mapped[str] = mapped_column(
        String(10), nullable=False, comment="风险等级(低/中/高/极高)",
    )
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False, comment="命中分值(0-100)")
    action: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="触发动作(pass/review/reject/freeze/report)",
    )
    is_enabled: Mapped[int] = mapped_column(Integer, default=1, comment="是否启用")
    priority: Mapped[int] = mapped_column(Integer, default=0, comment="优先级(越高越先执行)")
    description: Mapped[Optional[str]] = mapped_column(Text, comment="规则描述")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), default=datetime.now, comment="创建时间",
    )
    update_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), default=datetime.now, onupdate=datetime.now, comment="更新时间",
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="软删除时间(NULL=未删)",
    )

    @property
    def condition_dict(self) -> dict:
        if isinstance(self.rule_condition, str):
            return json.loads(self.rule_condition)
        return self.rule_condition


# ============================================================
# 事件审计
# ============================================================
class RiskEvent(Base):
    __tablename__ = "risk_event"

    event_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="事件ID")
    event_type: Mapped[str] = mapped_column(String(30), nullable=False, comment="事件类型")
    event_source_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="关联业务ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    event_data: Mapped[Optional[str]] = mapped_column(Text, comment="事件快照(JSON)")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), default=datetime.now, comment="创建时间",
    )

    __table_args__ = (
        Index("idx_risk_event_user_id", "user_id"),
        Index("idx_risk_event_create_time", "create_time"),
    )


class RiskFeature(Base):
    __tablename__ = "risk_feature"

    feature_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="特征ID")
    event_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="关联事件ID")
    entity_type: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="实体类型(用户/订单/地址)",
    )
    entity_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="实体ID")
    feature_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="特征名称")
    feature_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 4), comment="特征值")
    compute_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), comment="计算时间",
    )

    __table_args__ = (
        Index("idx_risk_feature_event_id", "event_id"),
        Index("idx_risk_feature_entity", "entity_type", "entity_id"),
    )


class RiskAssessment(Base):
    __tablename__ = "risk_assessment"

    assessment_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="评估ID")
    event_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="关联事件ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    rule_results: Mapped[Optional[str]] = mapped_column(Text, comment="规则结果(JSON)")
    rule_count: Mapped[int] = mapped_column(Integer, default=0, comment="命中规则数")
    final_score: Mapped[int] = mapped_column(Integer, nullable=False, comment="最终评分(0-100)")
    risk_level: Mapped[str] = mapped_column(String(10), nullable=False, comment="风险等级")
    decision: Mapped[str] = mapped_column(String(20), nullable=False, comment="决策(5级)")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), default=datetime.now, comment="创建时间",
    )
    ml_score: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 4), nullable=True, comment="XGBoost 拒绝概率 [0,1]",
    )
    ml_decision: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, comment="ML 决策: pass/review/reject/freeze/report",
    )

    __table_args__ = (
        Index("idx_risk_assessment_user_id", "user_id"),
        Index("idx_risk_assessment_decision", "decision"),
        Index("idx_risk_assessment_create_time", "create_time"),
    )


# ============================================================
# 案件管理
# ============================================================
class RiskCase(Base):
    __tablename__ = "risk_case"

    case_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="案件ID")
    assessment_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="关联评估ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    case_status: Mapped[str] = mapped_column(
        String(20), default="待审核", comment="案件状态",
    )
    case_category: Mapped[Optional[str]] = mapped_column(String(50), comment="案件分类")
    risk_detail: Mapped[Optional[str]] = mapped_column(Text, comment="风险详情(JSON)")
    reviewer: Mapped[Optional[str]] = mapped_column(String(50), comment="审核人")
    review_comment: Mapped[Optional[str]] = mapped_column(Text, comment="审核意见")
    review_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="审核时间")
    source_id: Mapped[Optional[str]] = mapped_column(String(50), comment="原始业务ID")
    event_type: Mapped[Optional[str]] = mapped_column(String(30), comment="触发案件的事件类型")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), default=datetime.now, comment="创建时间",
    )
    update_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), default=datetime.now, onupdate=datetime.now, comment="更新时间",
    )

    __table_args__ = (
        Index("idx_risk_case_status", "case_status"),
        Index("idx_risk_case_user_id", "user_id"),
    )


# ============================================================
# 黑名单 + 用户画像
# ============================================================
class RiskBlacklist(Base):
    __tablename__ = "risk_blacklist"

    blacklist_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="黑名单ID")
    blacklist_type: Mapped[str] = mapped_column(String(30), nullable=False, comment="黑名单类型(银行域)")
    blacklist_value: Mapped[str] = mapped_column(String(200), nullable=False, comment="黑名单值")
    reason: Mapped[Optional[str]] = mapped_column(Text, comment="加入原因")
    expire_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="过期时间(NULL=永久)")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), default=datetime.now, comment="创建时间",
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="软删除时间(NULL=未删)",
    )

    __table_args__ = (
        UniqueConstraint("blacklist_type", "blacklist_value", name="idx_blacklist_type_value"),
    )


class RiskUserProfile(Base):
    __tablename__ = "risk_user_profile"

    user_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="用户ID")
    risk_score: Mapped[int] = mapped_column(Integer, default=0, comment="综合风险评分(0-100)")
    risk_level: Mapped[str] = mapped_column(String(10), default="低", comment="风险等级")
    total_orders: Mapped[int] = mapped_column(Integer, default=0, comment="总交易数")
    total_refunds: Mapped[int] = mapped_column(Integer, default=0, comment="退拒数")
    refund_rate: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=0, comment="退款率")
    avg_order_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, comment="平均交易金额")
    address_count: Mapped[int] = mapped_column(Integer, default=0, comment="设备/地址数")
    complaint_count: Mapped[int] = mapped_column(Integer, default=0, comment="投诉次数")
    assessment_count: Mapped[int] = mapped_column(Integer, default=0, comment="评估次数")
    last_assessment_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="最近评估时间")
    profile_data: Mapped[Optional[str]] = mapped_column(Text, comment="扩展画像数据(JSON)")
    update_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), default=datetime.now, onupdate=datetime.now, comment="更新时间",
    )


# ============================================================
# 系统管理表
# ============================================================
class RiskActionLog(Base):
    __tablename__ = "risk_action_log"

    log_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="日志ID")
    operator: Mapped[str] = mapped_column(String(50), nullable=False, comment="操作人")
    action_type: Mapped[str] = mapped_column(String(30), nullable=False, comment="操作类型")
    target_type: Mapped[str] = mapped_column(String(20), nullable=False, comment="对象类型")
    target_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="对象ID")
    before_value: Mapped[Optional[str]] = mapped_column(Text, comment="变更前 JSON")
    after_value: Mapped[Optional[str]] = mapped_column(Text, comment="变更后 JSON")
    ip: Mapped[Optional[str]] = mapped_column(String(50), comment="操作 IP")
    remark: Mapped[Optional[str]] = mapped_column(String(500), comment="备注")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), default=datetime.now, comment="操作时间",
    )

    __table_args__ = (
        Index("idx_action_log_operator", "operator"),
        Index("idx_action_log_target", "target_type", "target_id"),
        Index("idx_action_log_create_time", "create_time"),
    )


class RiskAlert(Base):
    __tablename__ = "risk_alert"

    alert_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="告警ID")
    alert_type: Mapped[str] = mapped_column(String(20), nullable=False, comment="告警分类")
    alert_level: Mapped[str] = mapped_column(String(10), nullable=False, comment="告警等级")
    alert_title: Mapped[str] = mapped_column(String(200), nullable=False, comment="告警标题")
    alert_content: Mapped[Optional[str]] = mapped_column(Text, comment="告警详情")
    metric_name: Mapped[Optional[str]] = mapped_column(String(100), comment="指标名")
    metric_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6), comment="触发值")
    threshold: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6), comment="阈值")
    status: Mapped[str] = mapped_column(String(20), default="PENDING", comment="处理状态")
    handler: Mapped[Optional[str]] = mapped_column(String(50), comment="处理人")
    resolve_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="解决时间")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), default=datetime.now, comment="告警时间",
    )

    __table_args__ = (
        Index("idx_alert_status", "status"),
        Index("idx_alert_level", "alert_level"),
        Index("idx_alert_create_time", "create_time"),
    )
