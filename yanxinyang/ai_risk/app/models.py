# -*- coding: utf-8 -*-
"""数据模型层 —— 对应教学宝典《第 16 章：数据库 ER 图》 + 1.3「24 张表 = 17 业务 + 7 风控」

表结构以**声明式元数据**描述（Table/Column），一份定义三处复用：
    1. 生成 DDL（建表）
    2. 生成数据字典（前端「数据字段」页直接渲染）
    3. Base.metadata 汇总（宝典 13.3）

核心关系（宝典 16 章一句话）：
    一个 risk_event 产生 25 个 risk_feature + 1 个 risk_assessment；
    评估若 = 审核/拒绝 → 生成 1 个 risk_case；每用户对应 1 个 risk_user_profile。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Tuple

from app.database import Base


@dataclass
class Column:
    name: str
    type: str
    comment: str
    constraint: str = ""

    @property
    def ddl(self) -> str:
        # AUTO_PK 约束本身已含类型（"INTEGER PRIMARY KEY AUTOINCREMENT"）。
        # SQLite 要求自增列的声明类型**严格等于** INTEGER，
        # 拼成 "INTEGER INTEGER PRIMARY KEY AUTOINCREMENT" 会直接报
        # 「AUTOINCREMENT is only allowed on an INTEGER PRIMARY KEY」，故此处去重。
        if self.constraint.upper().startswith(self.type.upper() + " "):
            return f'"{self.name}" {self.constraint}'.strip()
        return f'"{self.name}" {self.type} {self.constraint}'.strip()


@dataclass
class Table:
    name: str
    comment: str
    group: str                                  # 业务 / 风控 / 审计
    columns: List[Column]
    indexes: List[str] = field(default_factory=list)

    @property
    def ddl(self) -> str:
        cols = ",\n  ".join(c.ddl for c in self.columns)
        return f'CREATE TABLE IF NOT EXISTS "{self.name}" (\n  {cols}\n)'

    def index_ddl(self) -> List[str]:
        out = []
        for idx, cols in enumerate(self.indexes):
            safe = cols.replace(",", "_").replace(" ", "")
            out.append(f'CREATE INDEX IF NOT EXISTS "idx_{self.name}_{safe}_{idx}" '
                       f'ON "{self.name}" ({cols})')
        return out


def C(name: str, type_: str, comment: str, constraint: str = "") -> Column:
    return Column(name, type_, comment, constraint)


PK = "PRIMARY KEY"
AUTO_PK = "INTEGER PRIMARY KEY AUTOINCREMENT"
NOW = "DEFAULT CURRENT_TIMESTAMP"

# ====================================================================== 枚举常量
EVENT_TYPES: Tuple[str, ...] = ("考试", "作业", "选课", "成绩申诉")
RISK_LEVELS: Tuple[str, ...] = ("低", "中", "高", "极高")
DECISIONS: Tuple[str, ...] = ("通过", "标记", "人工审核", "拒绝")
CASE_STATUSES: Tuple[str, ...] = ("待审核", "审核中", "已通过", "已拒绝", "已关闭")
RULE_CATEGORIES: Tuple[str, ...] = ("学术诚信", "学习行为", "账号安全", "成绩异常", "设备风险", "身份风险")
BLACKLIST_TYPES: Tuple[str, ...] = ("用户", "账号", "设备", "手机号", "IP")
ORDER_STATUSES: Tuple[str, ...] = ("待支付", "已支付", "已发货", "已完成", "已取消", "已退款")

_TABLES: List[Table] = []


def _t(table: Table) -> Table:
    _TABLES.append(table)
    Base.register(table)
    return table


# ====================================================================== 17 张业务表
USER_INFO = _t(Table("user_info", "用户主表", "业务", [
    C("user_id", "VARCHAR(32)", "用户 ID", PK),
    C("user_name", "VARCHAR(64)", "用户名", "NOT NULL"),
    C("phone", "VARCHAR(20)", "手机号"),
    C("email", "VARCHAR(64)", "邮箱"),
    C("user_level", "VARCHAR(16)", "会员等级", "DEFAULT '普通'"),
    C("user_status", "VARCHAR(16)", "账号状态：正常/冻结/注销", "DEFAULT '正常'"),
    C("credit_score", "INTEGER", "信用分 0-100", "DEFAULT 80"),
    C("register_time", "DATETIME", "注册时间", NOW),
    C("deleted_at", "DATETIME", "软删标记（业务查 IS NULL）"),
], indexes=["phone"]))

USER_ADDRESS = _t(Table("user_address", "关联账号/设备/IP（风控关联实体）", "业务", [
    C("address_id", "VARCHAR(32)", "地址 ID", PK),
    C("user_id", "VARCHAR(32)", "所属用户", "NOT NULL"),
    C("receiver_name", "VARCHAR(64)", "收货人"),
    C("receiver_phone", "VARCHAR(20)", "收货电话"),
    C("province", "VARCHAR(32)", "省"),
    C("city", "VARCHAR(32)", "市"),
    C("district", "VARCHAR(32)", "区"),
    C("detail_address", "VARCHAR(255)", "详细地址"),
    C("is_default", "INTEGER", "是否默认 0/1", "DEFAULT 0"),
    C("is_overseas", "INTEGER", "是否海外地址 0/1", "DEFAULT 0"),
    C("create_time", "DATETIME", "创建时间", NOW),
    C("deleted_at", "DATETIME", "软删标记"),
], indexes=["user_id"]))

ORDER_INFO = _t(Table("order_info", "学习行为记录表（考试/作业）", "业务", [
    C("order_id", "VARCHAR(32)", "订单 ID", PK),
    C("user_id", "VARCHAR(32)", "学习用户（越权校验核心字段）", "NOT NULL"),
    C("order_status", "VARCHAR(16)", "学习状态", "DEFAULT '待支付'"),
    C("total_amount", "DECIMAL(12,2)", "学习投入金额", "DEFAULT 0"),
    C("discount_amount", "DECIMAL(12,2)", "优惠金额", "DEFAULT 0"),
    C("pay_amount", "DECIMAL(12,2)", "实付金额", "DEFAULT 0"),
    C("receive_id", "VARCHAR(32)", "关联账号 ID"),
    C("order_source", "VARCHAR(16)", "学习入口：APP/H5/小程序/PC", "DEFAULT 'APP'"),
    C("create_time", "DATETIME", "学习行为时间", NOW),
    C("pay_time", "DATETIME", "支付时间"),
    C("deleted_at", "DATETIME", "软删标记"),
], indexes=["user_id", "create_time"]))

ORDER_ITEM = _t(Table("order_item", "订单明细", "业务", [
    C("item_id", "VARCHAR(32)", "明细 ID", PK),
    C("order_id", "VARCHAR(32)", "订单 ID", "NOT NULL"),
    C("product_id", "VARCHAR(32)", "商品 ID"),
    C("sku_id", "VARCHAR(32)", "SKU ID"),
    C("quantity", "INTEGER", "数量", "DEFAULT 1"),
    C("price", "DECIMAL(12,2)", "单价", "DEFAULT 0"),
    C("amount", "DECIMAL(12,2)", "小计", "DEFAULT 0"),
], indexes=["order_id"]))

ORDER_PAYMENT = _t(Table("order_payment", "缴费流水", "业务", [
    C("payment_id", "VARCHAR(32)", "支付 ID", PK),
    C("order_id", "VARCHAR(32)", "订单 ID", "NOT NULL"),
    C("user_id", "VARCHAR(32)", "用户 ID"),
    C("pay_channel", "VARCHAR(16)", "渠道：支付宝/微信/银行卡"),
    C("pay_amount", "DECIMAL(12,2)", "支付金额", "DEFAULT 0"),
    C("pay_status", "VARCHAR(16)", "支付状态", "DEFAULT '成功'"),
    C("pay_time", "DATETIME", "支付时间", NOW),
], indexes=["order_id"]))

PRODUCT_CATEGORY = _t(Table("product_category", "商品分类", "业务", [
    C("category_id", "VARCHAR(32)", "分类 ID", PK),
    C("category_name", "VARCHAR(64)", "分类名"),
    C("parent_id", "VARCHAR(32)", "父分类"),
    C("level", "INTEGER", "层级", "DEFAULT 1"),
]))

PRODUCT_INFO = _t(Table("product_info", "商品主表", "业务", [
    C("product_id", "VARCHAR(32)", "商品 ID", PK),
    C("product_name", "VARCHAR(128)", "商品名"),
    C("category_id", "VARCHAR(32)", "分类 ID"),
    C("brand", "VARCHAR(64)", "品牌"),
    C("price", "DECIMAL(12,2)", "标价", "DEFAULT 0"),
    C("status", "VARCHAR(16)", "上下架", "DEFAULT '在售'"),
], indexes=["category_id"]))

PRODUCT_SKU = _t(Table("product_sku", "商品 SKU", "业务", [
    C("sku_id", "VARCHAR(32)", "SKU ID", PK),
    C("product_id", "VARCHAR(32)", "商品 ID"),
    C("sku_name", "VARCHAR(128)", "规格名"),
    C("price", "DECIMAL(12,2)", "SKU 价", "DEFAULT 0"),
    C("stock", "INTEGER", "库存", "DEFAULT 0"),
], indexes=["product_id"]))

POSTSALE = _t(Table("postsale", "选课记录表", "业务", [
    C("postsale_id", "VARCHAR(32)", "售后单 ID", PK),
    C("order_id", "VARCHAR(32)", "订单 ID"),
    C("user_id", "VARCHAR(32)", "用户 ID", "NOT NULL"),
    C("postsale_type", "VARCHAR(16)", "类型：退货退款/仅退款/换货/维修"),
    C("postsale_status", "VARCHAR(16)", "状态", "DEFAULT '待处理'"),
    C("apply_amount", "DECIMAL(12,2)", "申请金额", "DEFAULT 0"),
    C("reason", "VARCHAR(255)", "申请原因"),
    C("create_time", "DATETIME", "申请时间", NOW),
    C("finish_time", "DATETIME", "完成时间"),
], indexes=["user_id", "order_id"]))

REFUND_RECORD = _t(Table("refund_record", "退款记录", "业务", [
    C("refund_id", "VARCHAR(32)", "退款 ID", PK),
    C("order_id", "VARCHAR(32)", "订单 ID"),
    C("postsale_id", "VARCHAR(32)", "售后单 ID"),
    C("user_id", "VARCHAR(32)", "用户 ID", "NOT NULL"),
    C("refund_amount", "DECIMAL(12,2)", "退款金额", "DEFAULT 0"),
    C("refund_status", "VARCHAR(16)", "退款状态", "DEFAULT '成功'"),
    C("refund_time", "DATETIME", "退款时间", NOW),
], indexes=["user_id"]))

LOGISTICS_ORDER = _t(Table("logistics_order", "物流单", "业务", [
    C("logistics_id", "VARCHAR(32)", "物流 ID", PK),
    C("order_id", "VARCHAR(32)", "订单 ID"),
    C("express_company", "VARCHAR(32)", "快递公司"),
    C("express_no", "VARCHAR(64)", "运单号"),
    C("logistics_status", "VARCHAR(16)", "物流状态", "DEFAULT '运输中'"),
    C("ship_time", "DATETIME", "发货时间"),
    C("sign_time", "DATETIME", "签收时间"),
], indexes=["order_id"]))

LOGISTICS_COMPLAINTS_RECORD = _t(Table("logistics_complaints_record", "成绩申诉记录表（event_type=成绩申诉 的 source 表）", "业务", [
    C("record_id", "INTEGER", "投诉记录 ID（int 类型，见宝典 10.4 字典驱动）", AUTO_PK),
    C("order_id", "VARCHAR(32)", "订单 ID"),
    C("user_id", "VARCHAR(32)", "用户 ID", "NOT NULL"),
    C("complaint_type", "VARCHAR(32)", "投诉类型：延迟/破损/丢件/态度"),
    C("complaint_content", "VARCHAR(255)", "投诉内容"),
    C("complaint_status", "VARCHAR(16)", "处理状态", "DEFAULT '待处理'"),
    C("is_verified", "INTEGER", "是否查实（label 投诉反推用）", "DEFAULT 0"),
    C("create_time", "DATETIME", "投诉时间", NOW),
], indexes=["user_id"]))

COMPLAINT_RECORD = _t(Table("complaint_record", "客服投诉记录", "业务", [
    C("complaint_id", "VARCHAR(32)", "投诉 ID", PK),
    C("user_id", "VARCHAR(32)", "用户 ID", "NOT NULL"),
    C("order_id", "VARCHAR(32)", "订单 ID"),
    C("complaint_type", "VARCHAR(32)", "投诉类型"),
    C("content", "VARCHAR(255)", "内容"),
    C("status", "VARCHAR(16)", "状态", "DEFAULT '待处理'"),
    C("create_time", "DATETIME", "投诉时间", NOW),
], indexes=["user_id"]))

CANCEL_RECORD = _t(Table("cancel_record", "订单取消记录", "业务", [
    C("cancel_id", "VARCHAR(32)", "取消 ID", PK),
    C("order_id", "VARCHAR(32)", "订单 ID"),
    C("user_id", "VARCHAR(32)", "用户 ID", "NOT NULL"),
    C("cancel_reason", "VARCHAR(255)", "取消原因"),
    C("cancel_time", "DATETIME", "取消时间", NOW),
], indexes=["user_id"]))

COUPON_RECORD = _t(Table("coupon_record", "优惠券使用记录", "业务", [
    C("coupon_record_id", "VARCHAR(32)", "记录 ID", PK),
    C("user_id", "VARCHAR(32)", "用户 ID"),
    C("order_id", "VARCHAR(32)", "订单 ID"),
    C("coupon_name", "VARCHAR(64)", "券名"),
    C("discount_amount", "DECIMAL(12,2)", "抵扣金额", "DEFAULT 0"),
    C("use_time", "DATETIME", "使用时间", NOW),
], indexes=["order_id"]))

LOGIN_LOG = _t(Table("login_log", "登录日志", "业务", [
    C("log_id", "INTEGER", "日志 ID", AUTO_PK),
    C("user_id", "VARCHAR(32)", "用户 ID"),
    C("login_ip", "VARCHAR(64)", "登录 IP"),
    C("login_city", "VARCHAR(32)", "登录城市"),
    C("login_device", "VARCHAR(64)", "登录设备"),
    C("login_status", "VARCHAR(16)", "成功/失败", "DEFAULT '成功'"),
    C("login_time", "DATETIME", "登录时间", NOW),
], indexes=["user_id"]))

DEVICE_INFO = _t(Table("device_info", "设备指纹", "业务", [
    C("device_id", "VARCHAR(64)", "设备 ID", PK),
    C("user_id", "VARCHAR(32)", "绑定用户"),
    C("device_type", "VARCHAR(32)", "设备类型"),
    C("os", "VARCHAR(32)", "操作系统"),
    C("device_fingerprint", "VARCHAR(128)", "指纹"),
    C("first_seen", "DATETIME", "首次出现", NOW),
    C("last_seen", "DATETIME", "最近出现", NOW),
], indexes=["user_id"]))

# ====================================================================== 7 张风控表
RISK_EVENT = _t(Table("risk_event", "风险事件（旅客）", "风控", [
    C("event_id", "VARCHAR(40)", "事件 ID", PK),
    C("event_type", "VARCHAR(16)", f"事件类型：{'/'.join(EVENT_TYPES)}", "NOT NULL"),
    C("user_id", "VARCHAR(32)", "用户 ID", "NOT NULL"),
    C("source_id", "VARCHAR(64)", "来源单号（订单/售后单/投诉记录）", "NOT NULL"),
    C("order_id", "VARCHAR(32)", "订单 ID"),
    C("receive_id", "VARCHAR(32)", "收货地址 ID（步骤 1c 自动补全）"),
    C("event_data", "TEXT", "事件原始数据 JSON"),
    C("client_ip", "VARCHAR(64)", "客户端 IP"),
    C("device_id", "VARCHAR(64)", "设备 ID"),
    C("event_time", "DATETIME", "事件时间", NOW),
    C("create_time", "DATETIME", "入库时间", NOW),
], indexes=["user_id", "event_type", "create_time"]))

RISK_FEATURE = _t(Table("risk_feature", "特征快照（1 事件 : 25 条）", "风控", [
    C("feature_id", "INTEGER", "特征 ID", AUTO_PK),
    C("event_id", "VARCHAR(40)", "所属事件", "NOT NULL"),
    C("feature_name", "VARCHAR(64)", "特征名", "NOT NULL"),
    C("feature_value", "DECIMAL(18,4)", "特征值", "DEFAULT 0"),
    C("feature_dim", "VARCHAR(16)", "维度：用户/学习/账号"),
    C("create_time", "DATETIME", "快照时间", NOW),
], indexes=["event_id", "feature_name"]))

RISK_ASSESSMENT = _t(Table("risk_assessment", "风险评估结果（1 事件 : 1 评估）", "风控", [
    C("assessment_id", "VARCHAR(40)", "评估 ID", PK),
    C("event_id", "VARCHAR(40)", "事件 ID", "NOT NULL"),
    C("user_id", "VARCHAR(32)", "用户 ID", "NOT NULL"),
    C("event_type", "VARCHAR(16)", "事件类型"),
    C("source_id", "VARCHAR(64)", "来源单号"),
    C("rule_score", "INTEGER", "规则分 0-100", "DEFAULT 0"),
    C("ml_score", "DECIMAL(8,2)", "ML 分 0-100", "DEFAULT 0"),
    C("ml_probability", "DECIMAL(8,6)", "XGBoost 原始概率", "DEFAULT 0"),
    C("final_score", "INTEGER", "融合分 = α×rule + β×ml", "DEFAULT 0"),
    C("risk_level", "VARCHAR(8)", f"风险等级：{'/'.join(RISK_LEVELS)}"),
    C("decision", "VARCHAR(16)", f"决策：{'/'.join(DECISIONS)}"),
    C("hit_rules", "TEXT", "命中规则 JSON 数组"),
    C("hit_rule_count", "INTEGER", "命中规则数", "DEFAULT 0"),
    C("is_veto", "INTEGER", "是否触发一票否决 0/1", "DEFAULT 0"),
    C("ml_loaded", "INTEGER", "ML 模型是否已加载 0/1", "DEFAULT 0"),
    C("weight_rule", "DECIMAL(4,2)", "α", "DEFAULT 0.5"),
    C("weight_ml", "DECIMAL(4,2)", "β", "DEFAULT 0.5"),
    C("feature_snapshot", "TEXT", "25 维特征 JSON"),
    C("reason", "VARCHAR(500)", "决策理由"),
    C("cost_ms", "INTEGER", "耗时毫秒", "DEFAULT 0"),
    C("label", "INTEGER", "训练标签（规则反推/人工标注）"),
    C("label_source", "VARCHAR(16)", "标签来源：人工标注/投诉反推/规则反推"),
    C("create_time", "DATETIME", "评估时间", NOW),
], indexes=["user_id", "decision", "create_time", "event_id"]))

RISK_CASE = _t(Table("risk_case", "风控案件（可疑旅客调查档案）", "风控", [
    C("case_id", "VARCHAR(40)", "案件 ID", PK),
    C("assessment_id", "VARCHAR(40)", "评估 ID", "NOT NULL"),
    C("event_id", "VARCHAR(40)", "事件 ID"),
    C("user_id", "VARCHAR(32)", "用户 ID", "NOT NULL"),
    C("source_id", "VARCHAR(64)", "来源单号"),
    C("event_type", "VARCHAR(16)", "事件类型"),
    C("case_status", "VARCHAR(16)", f"案件状态：{'/'.join(CASE_STATUSES)}", "DEFAULT '待审核'"),
    C("risk_level", "VARCHAR(8)", "风险等级"),
    C("final_score", "INTEGER", "融合分", "DEFAULT 0"),
    C("decision", "VARCHAR(16)", "原始决策"),
    C("hit_rules", "TEXT", "命中规则 JSON"),
    C("reviewer", "VARCHAR(64)", "审核人（system = 自动关闭）"),
    C("review_comment", "VARCHAR(500)", "审核意见"),
    C("review_time", "DATETIME", "审核时间"),
    C("create_time", "DATETIME", "创建时间", NOW),
    C("update_time", "DATETIME", "更新时间", NOW),
    C("deleted_at", "DATETIME", "软删标记"),
], indexes=["case_status", "user_id", "create_time"]))

RISK_RULE = _t(Table("risk_rule", "风控规则（违禁品清单）", "风控", [
    C("rule_id", "VARCHAR(16)", "规则 ID", PK),
    C("rule_name", "VARCHAR(64)", "规则名", "NOT NULL"),
    C("rule_category", "VARCHAR(16)", f"规则大类：{'/'.join(RULE_CATEGORIES)}"),
    C("event_type", "VARCHAR(16)", "限定事件类型（空 = 通用）"),
    C("rule_condition", "TEXT", "JSON 条件表达式（14 种 op）", "NOT NULL"),
    C("risk_level", "VARCHAR(8)", "风险等级（极高 = 一票否决）"),
    C("risk_score", "INTEGER", "规则分 0-100", "DEFAULT 0"),
    C("action", "VARCHAR(16)", "建议动作"),
    C("is_enabled", "INTEGER", "是否启用 0/1", "DEFAULT 1"),
    C("priority", "INTEGER", "优先级（降序匹配）", "DEFAULT 0"),
    C("description", "VARCHAR(255)", "规则说明"),
    C("hit_count", "INTEGER", "累计命中次数", "DEFAULT 0"),
    C("create_time", "DATETIME", "创建时间", NOW),
    C("update_time", "DATETIME", "更新时间", NOW),
    C("deleted_at", "DATETIME", "软删标记（2026-08-07 加）"),
], indexes=["is_enabled,priority", "rule_category"]))

RISK_BLACKLIST = _t(Table("risk_blacklist", "黑名单（失信旅客名单）", "风控", [
    C("blacklist_id", "INTEGER", "黑名单 ID", AUTO_PK),
    C("blacklist_type", "VARCHAR(16)", f"类型：{'/'.join(BLACKLIST_TYPES)}", "NOT NULL"),
    C("blacklist_value", "VARCHAR(128)", "黑名单值", "NOT NULL"),
    C("risk_level", "VARCHAR(8)", "风险等级", "DEFAULT '高'"),
    C("reason", "VARCHAR(255)", "拉黑原因"),
    C("source", "VARCHAR(32)", "来源：人工/系统/外部", "DEFAULT '人工'"),
    C("operator", "VARCHAR(64)", "操作人"),
    C("hit_count", "INTEGER", "命中次数", "DEFAULT 0"),
    C("expire_time", "DATETIME", "过期时间（空 = 永久）"),
    C("is_enabled", "INTEGER", "是否生效 0/1", "DEFAULT 1"),
    C("create_time", "DATETIME", "创建时间", NOW),
    C("deleted_at", "DATETIME", "软删标记"),
], indexes=["blacklist_type,blacklist_value"]))

RISK_USER_PROFILE = _t(Table("risk_user_profile", "用户风险画像（旅客常飞档案，1:1 user_info）", "风控", [
    C("user_id", "VARCHAR(32)", "用户 ID", PK),
    C("total_events", "INTEGER", "累计风控事件数", "DEFAULT 0"),
    C("risk_event_count", "INTEGER", "高危事件数（审核+拒绝）", "DEFAULT 0"),
    C("pass_count", "INTEGER", "通过次数", "DEFAULT 0"),
    C("mark_count", "INTEGER", "标记次数", "DEFAULT 0"),
    C("review_count", "INTEGER", "人工审核次数", "DEFAULT 0"),
    C("reject_count", "INTEGER", "拒绝次数", "DEFAULT 0"),
    C("case_count", "INTEGER", "案件数", "DEFAULT 0"),
    C("blacklist_hit_count", "INTEGER", "撞黑次数", "DEFAULT 0"),
    C("last_risk_level", "VARCHAR(8)", "最近风险等级"),
    C("last_decision", "VARCHAR(16)", "最近决策"),
    C("last_final_score", "INTEGER", "最近融合分", "DEFAULT 0"),
    C("max_final_score", "INTEGER", "历史最高融合分", "DEFAULT 0"),
    C("avg_final_score", "DECIMAL(8,2)", "平均融合分", "DEFAULT 0"),
    C("profile_level", "VARCHAR(8)", "画像等级", "DEFAULT '低'"),
    C("last_event_time", "DATETIME", "最近事件时间"),
    C("update_time", "DATETIME", "更新时间", NOW),
]))

# ====================================================================== 审计表（record_action 落库，宝典 9.4 / Anki 25）
RISK_ACTION_LOG = _t(Table("risk_action_log", "操作审计日志（record_action）", "审计", [
    C("log_id", "INTEGER", "日志 ID", AUTO_PK),
    C("operator", "VARCHAR(64)", "操作人（system = 系统自动）", "NOT NULL"),
    C("action_type", "VARCHAR(32)", "动作类型", "NOT NULL"),
    C("target_type", "VARCHAR(32)", "目标类型：案件/规则/黑名单/模型"),
    C("target_id", "VARCHAR(64)", "目标 ID"),
    C("before_value", "TEXT", "变更前"),
    C("after_value", "TEXT", "变更后"),
    C("remark", "VARCHAR(500)", "备注"),
    C("create_time", "DATETIME", "操作时间", NOW),
], indexes=["target_type,target_id", "create_time"]))

ALL_TABLES: Dict[str, Table] = {t.name: t for t in _TABLES}
BUSINESS_TABLES = [t for t in _TABLES if t.group == "业务"]
RISK_TABLES = [t for t in _TABLES if t.group == "风控"]
AUDIT_TABLES = [t for t in _TABLES if t.group == "审计"]


def iter_ddl() -> Iterator[str]:
    for table in _TABLES:
        yield table.ddl
        for idx in table.index_ddl():
            yield idx


def data_dictionary() -> List[Dict[str, object]]:
    """给前端「数据字典」页 —— 24 张表 + 审计表的全字段说明。"""
    return [{
        "table": t.name,
        "comment": t.comment,
        "group": t.group,
        "columns": [{"name": c.name, "type": c.type, "comment": c.comment,
                     "constraint": c.constraint} for c in t.columns],
    } for t in _TABLES]


TABLE_STATS = {
    "total": len(_TABLES),
    "business": len(BUSINESS_TABLES),
    "risk": len(RISK_TABLES),
    "audit": len(AUDIT_TABLES),
}
