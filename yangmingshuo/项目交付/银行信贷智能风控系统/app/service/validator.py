from app.config import EVENT_TYPES
from app.models_business import LoanApplication, LoginLog, Transaction
MODELS={"贷款申请":LoanApplication,"转账":Transaction,"登录":LoginLog}
def validate_event(db,event_type,source_id):
    if event_type not in EVENT_TYPES: raise ValueError(f"不支持的业务事件: {event_type}")
    if event_type in MODELS and not db.get(MODELS[event_type],source_id): raise ValueError(f"业务记录不存在: {source_id}")

