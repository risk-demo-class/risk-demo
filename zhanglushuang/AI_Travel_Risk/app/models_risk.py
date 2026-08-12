"""
旅游出行风控系统 - 风控核心表 ORM 模型.

对应 db/init.sql 中 9 张风控表:
risk_rule / risk_event / risk_feature / risk_assessment / risk_case /
risk_blacklist / risk_user_profile / risk_action_log / risk_alert
"""

import json
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Enum,
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


class RiskRule(Base):
    """风控规则配置表."""

    __tablename__ = "risk_rule"

    rule_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="规则ID")
    rule_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="规则名称")
    rule_category: Mapped[str] = mapped_column(
        Enum(
            "订单欺诈", "支付风险", "账户风险", "退改滥用", "签证风险", "设备风险", "跨境风险",
            name="rule_category_enum",
        ),
        nullable=False,
        comment="风险场景分类",
    )
    event_type: Mapped[str] = mapped_column(
        Enum(
            "下单", "支付", "退改申请", "签证申请", "拼团报名", "通用",
            name="rule_event_type_enum",
        ),
        nullable=False,
        server_default="通用",
        comment="适用事件类型",
    )
    rule_condition: Mapped[dict] = mapped_column(JSON, nullable=False, comment="条件表达式")
    risk_level: Mapped[str] = mapped_column(
        Enum("低", "中", "高", "极高", name="risk_level_enum"),
        nullable=False,
        comment="风险等级",
    )
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False, comment="命中分值(0-100)")
    action: Mapped[str] = mapped_column(
        Enum("通过", "标记", "人工审核", "拒绝", name="rule_action_enum"),
        nullable=False,
        comment="触发动作",
    )
    is_enabled: Mapped[int] = mapped_column(Integer, default=1, comment="是否启用")
    priority: Mapped[int] = mapped_column(Integer, default=0, comment="优先级")
    description: Mapped[Optional[str]] = mapped_column(Text, comment="规则描述")
    create_time: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        default=datetime.now,
        comment="创建时间",
    )
    update_time: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        default=datetime.now,
        onupdate=datetime.now,
        comment="更新时间",
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="软删除时间(NULL=未删)",
    )

    @property
    def condition_dict(self) -> dict:
        """兼容字符串 / JSON 两种存储方式."""
        if isinstance(self.rule_condition, str):
            return json.loads(self.rule_condition)
        return self.rule_condition or {}


class RiskEvent(Base):
    """风控事件审计表."""

    __tablename__ = "risk_event"

    event_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="事件ID")
    event_type: Mapped[str] = mapped_column(
        Enum("下单", "支付", "退改申请", "签证申请", "拼团报名", name="event_type_enum"),
        nullable=False,
        comment="事件类型",
    )
    event_source_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="关联业务ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    event_data: Mapped[Optional[dict]] = mapped_column(JSON, comment="事件快照")
    create_time: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        default=datetime.now,
        comment="创建时间",
    )

    __table_args__ = (
        Index("idx_risk_event_user_id", "user_id"),
        Index("idx_risk_event_create_time", "create_time"),
    )


class RiskFeature(Base):
    """风控特征快照表."""

    __tablename__ = "risk_feature"

    feature_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="特征ID",
    )
    event_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="关联事件ID")
    entity_type: Mapped[str] = mapped_column(
        Enum(
            "用户", "订单", "地址", "设备", "乘客", "语义",
            name="feature_entity_type_enum",
        ),
        nullable=False,
        comment="实体类型",
    )
    entity_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="实体ID")
    feature_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="特征名称")
    feature_value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(15, 4),
        comment="特征值",
    )
    compute_time: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        default=datetime.now,
        comment="计算时间",
    )

    __table_args__ = (
        Index("idx_risk_feature_event_id", "event_id"),
        Index("idx_risk_feature_entity", "entity_type", "entity_id"),
    )


class RiskAssessment(Base):
    """风控评估结果表."""

    __tablename__ = "risk_assessment"

    assessment_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="评估ID")
    event_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="关联事件ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    rule_results: Mapped[Optional[dict]] = mapped_column(JSON, comment="规则结果")
    rule_count: Mapped[int] = mapped_column(Integer, default=0, comment="命中规则数")
    final_score: Mapped[int] = mapped_column(Integer, nullable=False, comment="最终评分(0-100)")
    risk_level: Mapped[str] = mapped_column(
        Enum("低", "中", "高", "极高", name="risk_level_enum"),
        nullable=False,
        comment="风险等级",
    )
    decision: Mapped[str] = mapped_column(
        Enum("通过", "标记", "人工审核", "拒绝", name="rule_action_enum"),
        nullable=False,
        comment="决策",
    )
    ml_score: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2),
        comment="XGBoost 风险分(0-100)",
    )
    ml_probability: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(6, 4),
        comment="XGBoost 拒绝概率(0-1)",
    )
    ml_decision: Mapped[Optional[str]] = mapped_column(
        String(10),
        comment="ML 维度决策",
    )
    create_time: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        default=datetime.now,
        comment="创建时间",
    )

    __table_args__ = (
        Index("idx_risk_assessment_user_id", "user_id"),
        Index("idx_risk_assessment_decision", "decision"),
        Index("idx_risk_assessment_create_time", "create_time"),
    )


class RiskCase(Base):
    """风控案件表."""

    __tablename__ = "risk_case"

    case_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="案件ID")
    assessment_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="关联评估ID")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    case_status: Mapped[str] = mapped_column(
        Enum("待审核", "审核中", "已通过", "已拒绝", "已关闭", name="case_status_enum"),
        nullable=False,
        server_default="待审核",
        comment="案件状态",
    )
    case_category: Mapped[Optional[str]] = mapped_column(String(50), comment="案件分类")
    risk_detail: Mapped[Optional[dict]] = mapped_column(JSON, comment="风险详情")
    source_id: Mapped[Optional[str]] = mapped_column(String(50), comment="原始业务ID")
    event_type: Mapped[Optional[str]] = mapped_column(
        Enum(
            "下单", "支付", "退改申请", "签证申请", "拼团报名",
            name="case_event_type_enum",
        ),
        comment="触发案件的事件类型",
    )
    reviewer: Mapped[Optional[str]] = mapped_column(String(50), comment="审核人")
    review_comment: Mapped[Optional[str]] = mapped_column(Text, comment="审核意见")
    review_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="审核时间")
    create_time: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        default=datetime.now,
        comment="创建时间",
    )
    update_time: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        default=datetime.now,
        onupdate=datetime.now,
        comment="更新时间",
    )

    __table_args__ = (
        Index("idx_risk_case_status", "case_status"),
        Index("idx_risk_case_user_id", "user_id"),
        Index("idx_risk_case_source_id", "source_id"),
    )


class RiskBlacklist(Base):
    """风控黑名单表."""

    __tablename__ = "risk_blacklist"

    blacklist_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="黑名单ID",
    )
    blacklist_type: Mapped[str] = mapped_column(
        Enum(
            "用户", "手机号", "护照号", "签证号", "设备指纹", "支付账号", "IP",
            name="blacklist_type_enum",
        ),
        nullable=False,
        comment="黑名单类型",
    )
    blacklist_value: Mapped[str] = mapped_column(String(200), nullable=False, comment="黑名单值")
    reason: Mapped[Optional[str]] = mapped_column(Text, comment="加入原因")
    expire_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        comment="过期时间(NULL=永久)",
    )
    create_time: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        default=datetime.now,
        comment="创建时间",
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="软删除时间(NULL=未删)",
    )

    __table_args__ = (
        UniqueConstraint("blacklist_type", "blacklist_value", name="idx_blacklist_type_value"),
    )


class RiskUserProfile(Base):
    """用户风险画像表."""

    __tablename__ = "risk_user_profile"

    user_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="用户ID")
    risk_score: Mapped[int] = mapped_column(Integer, default=0, comment="综合风险评分(0-100)")
    risk_level: Mapped[str] = mapped_column(
        Enum("低", "中", "高", "极高", name="risk_level_enum"),
        server_default="低",
        comment="风险等级",
    )
    total_orders: Mapped[int] = mapped_column(Integer, default=0, comment="总订单数")
    total_refunds: Mapped[int] = mapped_column(Integer, default=0, comment="退改次数")
    refund_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        default=0,
        comment="退改率",
    )
    avg_order_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        default=0,
        comment="平均订单金额",
    )
    address_count: Mapped[int] = mapped_column(Integer, default=0, comment="常用乘客/联系人数量")
    complaint_count: Mapped[int] = mapped_column(Integer, default=0, comment="投诉次数")
    assessment_count: Mapped[int] = mapped_column(Integer, default=0, comment="评估次数")
    last_assessment_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        comment="最近评估时间",
    )
    profile_data: Mapped[Optional[dict]] = mapped_column(JSON, comment="扩展画像数据")
    update_time: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        default=datetime.now,
        onupdate=datetime.now,
        comment="更新时间",
    )


class RiskActionLog(Base):
    """风控操作审计日志表."""

    __tablename__ = "risk_action_log"

    log_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="日志ID",
    )
    operator: Mapped[str] = mapped_column(String(50), nullable=False, comment="操作人")
    action_type: Mapped[str] = mapped_column(
        Enum(
            "CREATE_RULE", "UPDATE_RULE", "TOGGLE_RULE", "DELETE_RULE",
            "REVIEW_CASE", "AUTO_REJECT_CASE", "AUTO_CLOSE_CASE",
            "ADD_BLACKLIST", "REMOVE_BLACKLIST", "LLM_REMARK",
            name="action_type_enum",
        ),
        nullable=False,
        comment="操作类型",
    )
    target_type: Mapped[str] = mapped_column(
        Enum("rule", "case", "blacklist", "model", name="action_target_type_enum"),
        nullable=False,
        comment="对象类型",
    )
    target_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="对象ID")
    before_value: Mapped[Optional[dict]] = mapped_column(JSON, comment="变更前")
    after_value: Mapped[Optional[dict]] = mapped_column(JSON, comment="变更后")
    ip: Mapped[Optional[str]] = mapped_column(String(50), comment="操作IP")
    remark: Mapped[Optional[str]] = mapped_column(String(500), comment="备注")
    create_time: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        default=datetime.now,
        comment="操作时间",
    )

    __table_args__ = (
        Index("idx_action_log_operator", "operator"),
        Index("idx_action_log_target", "target_type", "target_id"),
        Index("idx_action_log_create_time", "create_time"),
    )


class RiskAlert(Base):
    """风控告警记录表."""

    __tablename__ = "risk_alert"

    alert_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="告警ID",
    )
    alert_type: Mapped[str] = mapped_column(
        Enum("BUSINESS", "MODEL", "SYSTEM", "SECURITY", name="alert_type_enum"),
        nullable=False,
        comment="告警分类",
    )
    alert_level: Mapped[str] = mapped_column(
        Enum("P0", "P1", "P2", "P3", name="alert_level_enum"),
        nullable=False,
        comment="告警等级",
    )
    alert_title: Mapped[str] = mapped_column(String(200), nullable=False, comment="告警标题")
    alert_content: Mapped[Optional[str]] = mapped_column(Text, comment="告警详情")
    metric_name: Mapped[Optional[str]] = mapped_column(String(100), comment="指标名")
    metric_value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(20, 6),
        comment="触发值",
    )
    threshold: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6), comment="阈值")
    status: Mapped[str] = mapped_column(
        Enum("PENDING", "HANDLING", "RESOLVED", "IGNORED", name="alert_status_enum"),
        server_default="PENDING",
        comment="处理状态",
    )
    handler: Mapped[Optional[str]] = mapped_column(String(50), comment="处理人")
    resolve_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="解决时间")
    create_time: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        default=datetime.now,
        comment="告警时间",
    )

    __table_args__ = (
        Index("idx_alert_status", "status"),
        Index("idx_alert_level", "alert_level"),
        Index("idx_alert_create_time", "create_time"),
    )
