"""9 张风控核心表 ORM。

表的职责和老师项目保持一致，只对电商行业枚举、特征实体和用户画像摘要
进行银行化适配。
"""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models import (
    Base,
    Decision,
    EventType,
    RiskLevel,
    RuleEventType,
    enum_type,
)


class RuleCategory(StrEnum):
    ACCOUNT_SECURITY = "账户安全"
    TRANSFER_FRAUD = "转账欺诈"
    CARD_RISK = "信用卡风险"
    CREDIT_RISK = "信贷风险"
    DEVICE_RISK = "设备风险"
    IP_GEO_RISK = "IP与地域风险"


class FeatureEntityType(StrEnum):
    USER = "用户"
    TRANSACTION = "交易"
    DEVICE = "设备"
    CREDIT = "信贷"


class CaseStatus(StrEnum):
    PENDING = "待审核"
    REVIEWING = "审核中"
    APPROVED = "已通过"
    REJECTED = "已拒绝"
    CLOSED = "已关闭"


class BlacklistType(StrEnum):
    USER = "用户"
    ID_CARD = "身份证"
    BANK_ACCOUNT = "银行账户"
    BANK_CARD = "银行卡"
    BENEFICIARY_ACCOUNT = "收款账户"
    DEVICE_FINGERPRINT = "设备指纹"
    IP = "IP"
    MOBILE = "手机号"


class ActionType(StrEnum):
    CREATE_RULE = "CREATE_RULE"
    UPDATE_RULE = "UPDATE_RULE"
    TOGGLE_RULE = "TOGGLE_RULE"
    DELETE_RULE = "DELETE_RULE"
    REVIEW_CASE = "REVIEW_CASE"
    AUTO_REJECT_CASE = "AUTO_REJECT_CASE"
    AUTO_CLOSE_CASE = "AUTO_CLOSE_CASE"
    ADD_BLACKLIST = "ADD_BLACKLIST"
    REMOVE_BLACKLIST = "REMOVE_BLACKLIST"
    HANDLE_ALERT = "HANDLE_ALERT"
    RESOLVE_ALERT = "RESOLVE_ALERT"
    IGNORE_ALERT = "IGNORE_ALERT"


class ActionTargetType(StrEnum):
    RULE = "rule"
    CASE = "case"
    BLACKLIST = "blacklist"
    ALERT = "alert"


class AlertType(StrEnum):
    BUSINESS = "BUSINESS"
    MODEL = "MODEL"
    SYSTEM = "SYSTEM"
    SECURITY = "SECURITY"


class AlertLevel(StrEnum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class AlertStatus(StrEnum):
    PENDING = "PENDING"
    HANDLING = "HANDLING"
    RESOLVED = "RESOLVED"
    IGNORED = "IGNORED"


class RiskRule(Base):
    __tablename__ = "risk_rule"

    rule_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="规则ID")
    rule_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="规则名称")
    rule_category: Mapped[RuleCategory] = mapped_column(
        enum_type(RuleCategory, "rule_category_enum"), nullable=False, comment="银行风险场景分类"
    )
    event_type: Mapped[RuleEventType] = mapped_column(
        enum_type(RuleEventType, "rule_event_type_enum"),
        nullable=False,
        default=RuleEventType.COMMON,
        server_default=RuleEventType.COMMON.value,
        comment="适用事件类型",
    )
    rule_condition: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, comment="JSON条件表达式")
    risk_level: Mapped[RiskLevel] = mapped_column(
        enum_type(RiskLevel, "rule_risk_level_enum"), nullable=False, comment="风险等级"
    )
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False, comment="命中分值(0-100)")
    action: Mapped[Decision] = mapped_column(
        enum_type(Decision, "rule_action_enum"), nullable=False, comment="触发动作"
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="是否启用")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="优先级")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="规则描述")
    create_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="创建时间"
    )
    update_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now(), comment="更新时间"
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="软删除时间")

    __table_args__ = (
        CheckConstraint("risk_score BETWEEN 0 AND 100", name="risk_score_range"),
        Index("idx_risk_rule_event_enabled", "event_type", "is_enabled"),
    )


class RiskEvent(Base):
    __tablename__ = "risk_event"

    event_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="事件ID")
    event_type: Mapped[EventType] = mapped_column(
        enum_type(EventType, "risk_event_type_enum"), nullable=False, comment="银行事件类型"
    )
    event_source_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="关联业务ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="客户ID")
    event_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, comment="事件快照")
    create_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="创建时间"
    )

    __table_args__ = (
        Index("idx_risk_event_user_id", "user_id"),
        Index("idx_risk_event_source", "event_type", "event_source_id"),
        Index("idx_risk_event_create_time", "create_time"),
    )


class RiskFeature(Base):
    __tablename__ = "risk_feature"

    feature_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="特征ID")
    event_id: Mapped[str] = mapped_column(
        ForeignKey("risk_event.event_id"), nullable=False, comment="关联事件ID"
    )
    entity_type: Mapped[FeatureEntityType] = mapped_column(
        enum_type(FeatureEntityType, "feature_entity_type_enum"), nullable=False, comment="特征实体类型"
    )
    entity_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="实体ID")
    feature_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="特征名称")
    feature_value: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False, comment="特征值")
    compute_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="计算时间"
    )

    __table_args__ = (
        Index("idx_risk_feature_event_id", "event_id"),
        Index("idx_risk_feature_entity", "entity_type", "entity_id"),
        UniqueConstraint("event_id", "feature_name", name="uq_event_feature_name"),
    )


class RiskAssessment(Base):
    __tablename__ = "risk_assessment"

    assessment_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="评估ID")
    event_id: Mapped[str] = mapped_column(
        ForeignKey("risk_event.event_id"), nullable=False, unique=True, comment="关联事件ID"
    )
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="客户ID")
    rule_results: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True, comment="规则结果")
    rule_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="命中规则数")
    final_score: Mapped[int] = mapped_column(Integer, nullable=False, comment="最终评分(0-100)")
    risk_level: Mapped[RiskLevel] = mapped_column(
        enum_type(RiskLevel, "assessment_risk_level_enum"), nullable=False, comment="风险等级"
    )
    decision: Mapped[Decision] = mapped_column(
        enum_type(Decision, "assessment_decision_enum"), nullable=False, comment="最终决策"
    )
    ml_score: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4), nullable=True, comment="XGBoost风险概率[0,1]"
    )
    ml_decision: Mapped[str | None] = mapped_column(String(10), nullable=True, comment="ML维度决策")
    create_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="创建时间"
    )

    __table_args__ = (
        CheckConstraint("rule_count >= 0", name="rule_count_non_negative"),
        CheckConstraint("final_score BETWEEN 0 AND 100", name="final_score_range"),
        CheckConstraint("ml_score IS NULL OR (ml_score BETWEEN 0 AND 1)", name="ml_score_range"),
        Index("idx_risk_assessment_user_id", "user_id"),
        Index("idx_risk_assessment_decision", "decision"),
        Index("idx_risk_assessment_create_time", "create_time"),
    )


class RiskCase(Base):
    __tablename__ = "risk_case"

    case_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="案件ID")
    assessment_id: Mapped[str] = mapped_column(
        ForeignKey("risk_assessment.assessment_id"), nullable=False, unique=True, comment="关联评估ID"
    )
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="客户ID")
    case_status: Mapped[CaseStatus] = mapped_column(
        enum_type(CaseStatus, "case_status_enum"),
        nullable=False,
        default=CaseStatus.PENDING,
        server_default=CaseStatus.PENDING.value,
        comment="案件状态",
    )
    case_category: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="案件分类")
    risk_detail: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, comment="风险详情")
    source_id: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="原始业务ID")
    event_type: Mapped[EventType | None] = mapped_column(
        enum_type(EventType, "case_event_type_enum"), nullable=True, comment="触发案件的事件类型"
    )
    reviewer: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="审核人")
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True, comment="审核意见")
    review_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="审核时间")
    create_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="创建时间"
    )
    update_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now(), comment="更新时间"
    )

    __table_args__ = (
        Index("idx_risk_case_status", "case_status"),
        Index("idx_risk_case_user_id", "user_id"),
        Index("idx_risk_case_source_id", "source_id"),
    )


class RiskBlacklist(Base):
    __tablename__ = "risk_blacklist"

    blacklist_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="黑名单ID")
    blacklist_type: Mapped[BlacklistType] = mapped_column(
        enum_type(BlacklistType, "blacklist_type_enum"), nullable=False, comment="银行黑名单类型"
    )
    blacklist_value: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="对象ID、哈希值或脱敏值"
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True, comment="加入原因")
    expire_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="过期时间")
    create_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="创建时间"
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="软删除时间")

    __table_args__ = (
        UniqueConstraint("blacklist_type", "blacklist_value", name="uq_blacklist_type_value"),
        Index("idx_blacklist_active", "blacklist_type", "deleted_at", "expire_time"),
    )


class RiskUserProfile(Base):
    __tablename__ = "risk_user_profile"

    user_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="客户ID")
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="综合风险评分")
    risk_level: Mapped[RiskLevel] = mapped_column(
        enum_type(RiskLevel, "profile_risk_level_enum"),
        nullable=False,
        default=RiskLevel.LOW,
        server_default=RiskLevel.LOW.value,
        comment="风险等级",
    )
    txn_count_30d: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="近30天交易笔数")
    txn_amount_30d: Mapped[Decimal] = mapped_column(
        Numeric(16, 2), nullable=False, default=0, comment="近30天交易金额"
    )
    failed_login_count_30d: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="近30天失败登录次数"
    )
    device_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="关联设备数")
    high_risk_ip_count_30d: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="近30天高风险IP次数"
    )
    loan_application_count_30d: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="近30天贷款申请次数"
    )
    debt_ratio: Mapped[Decimal] = mapped_column(
        Numeric(6, 4), nullable=False, default=0, comment="最近负债率"
    )
    assessment_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="评估次数")
    last_assessment_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="最近评估时间")
    profile_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, comment="扩展银行风险画像")
    update_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now(), comment="更新时间"
    )

    __table_args__ = (
        CheckConstraint("risk_score BETWEEN 0 AND 100", name="risk_score_range"),
        CheckConstraint("debt_ratio BETWEEN 0 AND 1", name="debt_ratio_range"),
    )


class RiskActionLog(Base):
    __tablename__ = "risk_action_log"

    log_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="日志ID")
    operator: Mapped[str] = mapped_column(String(50), nullable=False, comment="操作人")
    action_type: Mapped[ActionType] = mapped_column(
        enum_type(ActionType, "action_type_enum"), nullable=False, comment="操作类型"
    )
    target_type: Mapped[ActionTargetType] = mapped_column(
        enum_type(ActionTargetType, "action_target_type_enum"), nullable=False, comment="对象类型"
    )
    target_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="对象ID")
    before_value: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, comment="变更前")
    after_value: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, comment="变更后")
    ip: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="操作IP")
    remark: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="备注")
    create_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="操作时间"
    )

    __table_args__ = (
        Index("idx_action_log_operator", "operator"),
        Index("idx_action_log_target", "target_type", "target_id"),
        Index("idx_action_log_create_time", "create_time"),
    )


class RiskAlert(Base):
    __tablename__ = "risk_alert"

    alert_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="告警ID")
    alert_type: Mapped[AlertType] = mapped_column(
        enum_type(AlertType, "alert_type_enum"), nullable=False, comment="告警分类"
    )
    alert_level: Mapped[AlertLevel] = mapped_column(
        enum_type(AlertLevel, "alert_level_enum"), nullable=False, comment="告警等级"
    )
    alert_title: Mapped[str] = mapped_column(String(200), nullable=False, comment="告警标题")
    alert_content: Mapped[str | None] = mapped_column(Text, nullable=True, comment="告警详情")
    metric_name: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="指标名")
    metric_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True, comment="触发值")
    threshold: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True, comment="阈值")
    status: Mapped[AlertStatus] = mapped_column(
        enum_type(AlertStatus, "alert_status_enum"),
        nullable=False,
        default=AlertStatus.PENDING,
        server_default=AlertStatus.PENDING.value,
        comment="处理状态",
    )
    handler: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="处理人")
    resolve_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="解决时间")
    create_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="告警时间"
    )

    __table_args__ = (
        Index("idx_alert_status", "status"),
        Index("idx_alert_level", "alert_level"),
        Index("idx_alert_create_time", "create_time"),
    )


RISK_TABLE_NAMES = (
    "risk_rule",
    "risk_event",
    "risk_feature",
    "risk_assessment",
    "risk_case",
    "risk_blacklist",
    "risk_user_profile",
    "risk_action_log",
    "risk_alert",
)

