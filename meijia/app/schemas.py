"""与教育 ORM 同步的最小 Pydantic 输入/输出模型。"""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserCreate(BaseModel):
    user_id: str = Field(max_length=50)
    name: str = Field(max_length=100)
    role: Literal["学生", "家长", "老师"]
    student_id: str | None = Field(default=None, max_length=50)
    real_name_status: Literal["未认证", "认证中", "已认证", "认证失败"] = "未认证"
    register_at: datetime


class UserResponse(UserCreate, ORMModel):
    created_at: datetime
    updated_at: datetime


class CourseCreate(BaseModel):
    course_id: str
    name: str
    category: str
    price: Decimal = Field(ge=0)
    teacher_id: str
    total_hours: Decimal = Field(gt=0)
    course_status: Literal["草稿", "已上架", "已下架", "已归档"] = "草稿"


class OrderCreate(BaseModel):
    order_id: str
    user_id: str
    learner_user_id: str
    course_id: str
    total_amount: Decimal = Field(ge=0)
    currency: str = "CNY"
    study_goal: str | None = None
    expected_finish_days: int | None = Field(default=None, gt=0)


class RefundCreate(BaseModel):
    refund_id: str
    order_id: str
    requested_by_user_id: str
    reason: str
    study_minutes_before_refund: int = Field(ge=0)
    requested_amount: Decimal = Field(gt=0)


class RiskCheckRequest(BaseModel):
    event_type: str
    source_id: str | None = None
    user_id: str
    order_id: str | None = None
    refund_id: str | None = None
    live_session_id: str | None = None
    event_data: dict | None = None


class RiskCheckResponse(BaseModel):
    assessment_id: str
    event_id: str
    user_id: str
    final_score: int
    risk_level: str
    decision: str
    rule_count: int
    triggered_rules: list[dict]
    features: dict[str, float]
    blocked_by: str | None = None
    ml_score: float | None = None
    ml_decision: str | None = None


class CaseReviewRequest(BaseModel):
    decision: Literal["已通过", "已拒绝", "已关闭"]
    reviewer: str = Field(min_length=1, max_length=50)
    review_comment: str | None = Field(default=None, max_length=1000)


class BlacklistCreate(BaseModel):
    type: Literal["用户ID", "学号", "身份证", "设备指纹", "直播账号"]
    value: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=500)
    expire_at: datetime | None = None
    created_by: str = Field(default="admin", max_length=50)


class RuleResponse(ORMModel):
    rule_id: str
    rule_name: str
    event_type: str
    risk_level: str
    risk_score: int
    action: str
    enabled: bool


class RuleUpdate(BaseModel):
    rule_condition: dict | None = None
    risk_level: Literal["低", "中", "高", "极高"] | None = None
    risk_score: int | None = Field(default=None, ge=0, le=100)
    action: Literal["通过", "标记", "人工审核", "拒绝"] | None = None
    priority: int | None = None
    description: str | None = Field(default=None, max_length=500)
    version: int = Field(ge=1, description="客户端读取到的当前版本，用于防止并发覆盖")


class AgentChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: str | None = None


class AgentChatResponse(BaseModel):
    reply: str
    session_id: str


class AssessmentResponse(ORMModel):
    assessment_id: str
    event_id: str
    user_id: str
    feature_snapshot: dict
    rule_results: list
    final_score: int
    risk_level: str
    decision: str
    ml_score: float | None = None
    ml_decision: str | None = None
