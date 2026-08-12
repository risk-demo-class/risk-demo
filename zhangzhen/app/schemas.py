"""第一阶段公共响应模型。

后续的 RiskCheckRequest/RiskCheckResponse 会在主链路阶段加入本文件。
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class HealthResponse(ApiModel):
    status: Literal["ok"]
    service: str
    environment: str
    business_table_count: int
    risk_table_count: int
    registered_table_count: int


class ReadinessResponse(ApiModel):
    status: Literal["ready"]
    database: Literal["available"]

