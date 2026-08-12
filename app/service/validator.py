"""Service 层步骤一：校验事件类型、来源记录和用户归属。"""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import CredentialVerification, Enrollment, RefundRequest
from app.schemas import RiskCheckRequest


def validate_source_ownership(session: Session, request: RiskCheckRequest) -> Enrollment | RefundRequest:
    """校验教育事件来源存在，并确保请求用户拥有对应业务记录。"""
    if request.event_type == "课程报名":
        enrollment = session.get(Enrollment, request.source_id)
        if enrollment is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="报名记录不存在。")
        if enrollment.user_id != request.user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="报名记录不属于该用户。")
        return enrollment
    if request.event_type == "退费申请":
        refund = session.get(RefundRequest, request.source_id)
        if refund is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="退款申请不存在。")
        enrollment = session.get(Enrollment, refund.enrollment_id)
        if enrollment is None or enrollment.user_id != request.user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="退款申请不属于该用户。")
        return refund
    if request.event_type == "学历认证":
        verification = session.get(CredentialVerification, request.source_id)
        if verification is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="学历认证记录不存在。")
        if verification.user_id != request.user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="学历认证记录不属于该用户。")
        return verification
    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="不支持的教育风控事件。")
