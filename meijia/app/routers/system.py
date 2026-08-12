from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_session

router = APIRouter(prefix="/api", tags=["系统"])


@router.get("/health")
def health(db: Session = Depends(get_session)):
    db.execute(select(1))
    from app.engine import ml_model
    from app.scheduler import is_running

    return {
        "status": "ok",
        "service": "education-risk",
        "ml_model_loaded": ml_model.is_model_loaded(),
        "scheduler_running": is_running(),
        "alerts_interval_min": _scheduler_interval(),
    }


def _scheduler_interval():
    from app.config import settings
    return settings.ALERT_SCHEDULER_INTERVAL_MIN
