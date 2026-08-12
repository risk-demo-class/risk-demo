"""教育业务数据接口 — 课程/报名/缴费/退费查询"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import (
    CourseInfo, Enrollment, ExamRecord, PaymentRecord, RefundRecord, UserInfo,
)

router = APIRouter(prefix="/api/business", tags=["业务数据"])


@router.get("/courses")
async def list_courses(db: AsyncSession = Depends(get_db)):
    courses = (await db.execute(
        select(CourseInfo).where(CourseInfo.is_deleted.is_(False)))).scalars().all()
    return [{"course_id": c.course_id, "course_name": c.course_name,
             "price": float(c.price), "category_id": c.category_id,
             "school_id": c.school_id} for c in courses]


@router.get("/enrollments")
async def list_enrollments(user_id: str | None = None, db: AsyncSession = Depends(get_db)):
    stmt = select(Enrollment).where(Enrollment.is_deleted.is_(False)).order_by(Enrollment.create_time.desc())
    if user_id:
        stmt = stmt.where(Enrollment.user_id == user_id)
    rows = (await db.execute(stmt)).scalars().all()
    return [{
        "enrollment_id": e.enrollment_id, "user_id": e.user_id, "status": e.status,
        "total_amount": float(e.total_amount), "create_time": e.create_time.isoformat() if e.create_time else None,
    } for e in rows]


@router.get("/payments")
async def list_payments(user_id: str | None = None, db: AsyncSession = Depends(get_db)):
    stmt = select(PaymentRecord).where(PaymentRecord.is_deleted.is_(False)).order_by(PaymentRecord.pay_time.desc())
    if user_id:
        stmt = stmt.where(PaymentRecord.user_id == user_id)
    rows = (await db.execute(stmt)).scalars().all()
    return [{
        "payment_id": p.payment_id, "enrollment_id": p.enrollment_id, "user_id": p.user_id,
        "amount": float(p.amount), "pay_method": p.pay_method, "status": p.status,
        "pay_time": p.pay_time.isoformat() if p.pay_time else None,
    } for p in rows]


@router.get("/refunds")
async def list_refunds(user_id: str | None = None, db: AsyncSession = Depends(get_db)):
    stmt = select(RefundRecord).where(RefundRecord.is_deleted.is_(False)).order_by(RefundRecord.apply_time.desc())
    if user_id:
        stmt = stmt.where(RefundRecord.user_id == user_id)
    rows = (await db.execute(stmt)).scalars().all()
    return [{
        "refund_id": r.refund_id, "enrollment_id": r.enrollment_id, "user_id": r.user_id,
        "amount": float(r.amount), "reason": r.reason, "status": r.status,
        "apply_time": r.apply_time.isoformat() if r.apply_time else None,
    } for r in rows]


@router.get("/exams")
async def list_exams(user_id: str | None = None, db: AsyncSession = Depends(get_db)):
    stmt = select(ExamRecord).where(ExamRecord.is_deleted.is_(False)).order_by(ExamRecord.exam_time.desc())
    if user_id:
        stmt = stmt.where(ExamRecord.user_id == user_id)
    rows = (await db.execute(stmt)).scalars().all()
    return [{
        "exam_id": e.exam_id, "user_id": e.user_id, "course_id": e.course_id,
        "duration_seconds": e.duration_seconds, "score": float(e.score),
        "cheat_flag": e.cheat_flag, "exam_time": e.exam_time.isoformat() if e.exam_time else None,
    } for e in rows]
