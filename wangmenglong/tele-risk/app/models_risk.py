"""
电信风控系统 - 风控表 ORM (9 张)
================================
参照 ai_risk/app/models_risk.py 设计, 适配电信业务 (号卡 msisdn 为核心枢纽).

  规则配置: TelecomRiskRule
  事件审计: TelecomRiskEvent / TelecomRiskFeature / TelecomRiskAssessment
  案件管理: TelecomRiskCase
  黑名单:   TelecomRiskBlacklist (号卡/客户/设备/渠道)
  号卡画像: TelecomCardProfile
  操作日志: TelecomRiskActionLog
  告警记录: TelecomRiskAlert
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

class TelecomRiskRule(Base):
    """电信风控规则表 (JSON 条件表达式, 参照 ai_risk RiskRule).

    event_type 取值: 开户/通话/国际来电/短信发送/物联网激活/通用
    risk_level: 低/中/高/极高 (极高 = 一票否决)
    action: 通过/标记/人工审核/拒绝/关停号码/推送公安
    """
    __tablename__ = "telecom_risk_rule"

    rule_id: Mapped[str] = mapped_column(String(20), primary_key=True, comment="规则ID (R+3位)")
    rule_name: Mapped[str] = mapped_column(String(80), nullable=False, comment="规则名称")
    rule_category: Mapped[str] = mapped_column(String(30), nullable=False, comment="规则类别")
    event_type: Mapped[str] = mapped_column(String(20), nullable=False, default="通用", comment="事件类型")
    rule_condition: Mapped[str] = mapped_column(Text, nullable=False, comment="条件 JSON")
    risk_level: Mapped[str] = mapped_column(String(10), nullable=False, comment="风险等级 (低/中/高/极高)")
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False, comment="风险分 (0-100)")
    action: Mapped[str] = mapped_column(String(20), nullable=False, comment="处置动作")
    is_enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="是否启用 (0/1)")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=50, comment="优先级 (高先匹配)")
    description: Mapped[Optional[str]] = mapped_column(String(200), comment="描述")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), default=datetime.now, comment="创建时间",
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="软删时间 (NULL=未删)")

    @property
    def condition_dict(self) -> dict:
        """rule_condition JSON 字符串 → dict (跟 ai_risk RiskRule 行为一致)."""
        if not self.rule_condition:
            return {}
        try:
            return json.loads(self.rule_condition)
        except (json.JSONDecodeError, TypeError):
            return {}


# ============================================================
# 事件审计
# ============================================================

class TelecomRiskEvent(Base):
    """风控事件表. 每次风控检查记 1 行, event_id 被 feature/assessment 引用."""
    __tablename__ = "telecom_risk_event"

    event_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="事件ID (evt+ULID)")
    event_type: Mapped[str] = mapped_column(String(20), nullable=False, comment="事件类型 (开户/通话/国际来电/短信发送/物联网激活)")
    event_source_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="关联业务ID (业务单号/CDR ID 等)")
    msisdn: Mapped[str] = mapped_column(String(11), nullable=False, comment="号卡 (核心枢纽)")
    event_data: Mapped[Optional[str]] = mapped_column(Text, comment="事件快照 JSON")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), default=datetime.now, comment="创建时间",
    )

    __table_args__ = (
        Index("idx_telecom_event_msisdn", "msisdn"),
        Index("idx_telecom_event_create_time", "create_time"),
    )


class TelecomRiskFeature(Base):
    """特征快照表. 每次评估把 25 维特征落库, 审计回溯 + 训练取数."""
    __tablename__ = "telecom_risk_feature"

    feature_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="特征ID")
    event_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="关联事件ID")
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False, comment="实体类型 (号卡/客户/设备/渠道/物联网)")
    entity_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="实体ID")
    feature_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="特征名称")
    feature_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 4), comment="特征值")
    compute_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), comment="计算时间",
    )

    __table_args__ = (
        Index("idx_telecom_feature_event_id", "event_id"),
        Index("idx_telecom_feature_entity", "entity_type", "entity_id"),
    )


class TelecomRiskAssessment(Base):
    """风控评估结果表. final_score + risk_level + decision + 命中规则详情."""
    __tablename__ = "telecom_risk_assessment"

    assessment_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="评估ID (ast+ULID)")
    event_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="关联事件ID")
    msisdn: Mapped[str] = mapped_column(String(11), nullable=False, comment="号卡")
    rule_results: Mapped[Optional[str]] = mapped_column(Text, comment="命中规则详情 JSON")
    rule_count: Mapped[int] = mapped_column(Integer, default=0, comment="命中规则数")
    final_score: Mapped[int] = mapped_column(Integer, nullable=False, comment="最终评分 (0-100)")
    risk_level: Mapped[str] = mapped_column(String(10), nullable=False, comment="风险等级 (低/中/高/极高)")
    decision: Mapped[str] = mapped_column(String(20), nullable=False, comment="决策 (通过/标记/人工审核/拒绝/关停号码)")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), default=datetime.now, comment="创建时间",
    )
    # XGBoost 双轨融合
    ml_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 4), nullable=True, comment="XGBoost P(高风险) [0,1]")
    ml_decision: Mapped[Optional[str]] = mapped_column(String(10), nullable=True, comment="ML 决策")

    __table_args__ = (
        Index("idx_telecom_assessment_msisdn", "msisdn"),
        Index("idx_telecom_assessment_decision", "decision"),
        Index("idx_telecom_assessment_create_time", "create_time"),
    )


# ============================================================
# 案件管理
# ============================================================

class TelecomRiskCase(Base):
    """案件表. 决策=人工审核/拒绝/关停号码 时建案, 走人工处置流程."""
    __tablename__ = "telecom_risk_case"

    case_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="案件ID (cas+ULID)")
    assessment_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="关联评估ID")
    msisdn: Mapped[str] = mapped_column(String(11), nullable=False, comment="号卡")
    case_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="待审核", comment="案件状态 (待审核/审核中/已通过/已拒绝/已关闭/已关停)",
    )
    case_category: Mapped[Optional[str]] = mapped_column(String(30), comment="案件分类 (通话欺诈/设备欺诈/...)")
    risk_detail: Mapped[Optional[str]] = mapped_column(Text, comment="风险详情 JSON")
    reviewer: Mapped[Optional[str]] = mapped_column(String(50), comment="审核人")
    review_comment: Mapped[Optional[str]] = mapped_column(Text, comment="审核意见")
    review_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="审核时间")
    # 业务回溯字段 (重做检查用)
    source_id: Mapped[Optional[str]] = mapped_column(String(50), comment="原始业务ID")
    event_type: Mapped[Optional[str]] = mapped_column(String(20), comment="触发案件的事件类型")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), default=datetime.now, comment="创建时间",
    )
    update_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), default=datetime.now, onupdate=datetime.now, comment="更新时间",
    )

    __table_args__ = (
        Index("idx_telecom_case_status", "case_status"),
        Index("idx_telecom_case_msisdn", "msisdn"),
    )


# ============================================================
# 黑名单 + 号卡画像
# ============================================================

class TelecomRiskBlacklist(Base):
    """黑名单表. 类型: 号卡(msisdn)/客户(customer_id)/设备(imei)/渠道(channel_id).

    撞黑 → 直接拒绝/关停, 不走 7 步决策. 反诈法第 21 条失信名单.
    """
    __tablename__ = "telecom_risk_blacklist"

    blacklist_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="黑名单ID")
    blacklist_type: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="黑名单类型 (号卡/客户/设备/渠道)",
    )
    blacklist_value: Mapped[str] = mapped_column(String(50), nullable=False, comment="黑名单值")
    reason: Mapped[Optional[str]] = mapped_column(Text, comment="加入原因")
    expire_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="过期时间 (NULL=永久)")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), default=datetime.now, comment="创建时间",
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="软删时间 (NULL=未删)")

    __table_args__ = (
        UniqueConstraint("blacklist_type", "blacklist_value", name="idx_telecom_blacklist_type_value"),
    )


class TelecomCardProfile(Base):
    """号卡风险画像表. upsert 模式: 每次评估更新, 累积号卡风险历史."""
    __tablename__ = "telecom_card_profile"

    msisdn: Mapped[str] = mapped_column(String(11), primary_key=True, comment="号卡")
    risk_score: Mapped[int] = mapped_column(Integer, default=0, comment="综合风险评分 (0-100)")
    risk_level: Mapped[str] = mapped_column(String(10), default="低", comment="风险等级")
    assessment_count: Mapped[int] = mapped_column(Integer, default=0, comment="评估次数")
    last_assessment_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="最近评估时间")
    profile_data: Mapped[Optional[str]] = mapped_column(Text, comment="扩展画像数据 JSON")
    update_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), default=datetime.now(), onupdate=datetime.now, comment="更新时间",
    )


# ============================================================
# 操作审计日志 + 告警记录 (系统管理)
# ============================================================

class TelecomRiskActionLog(Base):
    """操作审计日志表. 规则/案件/黑名单变更都写一行, 合规审计 + 追责."""
    __tablename__ = "telecom_risk_action_log"

    log_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="日志ID")
    operator: Mapped[str] = mapped_column(String(50), nullable=False, comment="操作人(admin/system/ai_agent)")
    action_type: Mapped[str] = mapped_column(
        String(30), nullable=False,
        comment="操作类型 (CREATE_RULE/UPDATE_RULE/TOGGLE_RULE/DELETE_RULE/REVIEW_CASE/AUTO_REJECT_CASE/AUTO_CLOSE_CASE/ADD_BLACKLIST/REMOVE_BLACKLIST/AUTO_HALT_CARD)",
    )
    target_type: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="对象类型 (rule/case/blacklist/assessment)",
    )
    target_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="对象ID")
    before_value: Mapped[Optional[str]] = mapped_column(Text, comment="变更前 JSON (NULL=新增)")
    after_value: Mapped[Optional[str]] = mapped_column(Text, comment="变更后 JSON (NULL=删除)")
    ip: Mapped[Optional[str]] = mapped_column(String(50), comment="操作IP")
    remark: Mapped[Optional[str]] = mapped_column(String(500), comment="备注")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), default=datetime.now(), comment="操作时间",
    )

    __table_args__ = (
        Index("idx_action_log_operator", "operator"),
        Index("idx_action_log_target", "target_type", "target_id"),
        Index("idx_action_log_create_time", "create_time"),
    )


class TelecomRiskAlert(Base):
    """告警记录表. 风控系统自我监控 (规则命中率/案件积压/模型漂移等)."""
    __tablename__ = "telecom_risk_alert"

    alert_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="告警ID")
    alert_type: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="告警分类 (BUSINESS/MODEL/SYSTEM/SECURITY)",
    )
    alert_level: Mapped[str] = mapped_column(
        String(5), nullable=False, comment="告警等级 (P0=致命/P1=高/P2=中/P3=提示)",
    )
    alert_title: Mapped[str] = mapped_column(String(200), nullable=False, comment="告警标题")
    alert_content: Mapped[Optional[str]] = mapped_column(Text, comment="告警详情")
    metric_name: Mapped[Optional[str]] = mapped_column(String(100), comment="指标名")
    metric_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6), comment="触发值")
    threshold: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6), comment="阈值")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PENDING", comment="处理状态 (PENDING/HANDLING/RESOLVED/IGNORED)",
    )
    handler: Mapped[Optional[str]] = mapped_column(String(50), comment="处理人")
    resolve_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="解决时间")
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), default=datetime.now(), comment="告警时间",
    )

    __table_args__ = (
        Index("idx_alert_status", "status"),
        Index("idx_alert_level", "alert_level"),
        Index("idx_alert_create_time", "create_time"),
    )
