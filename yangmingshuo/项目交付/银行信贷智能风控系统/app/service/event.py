import json, uuid
from datetime import datetime
from sqlalchemy import select
from app.engine.feature import compute_loan_features,compute_login_features,compute_transaction_features,compute_user_features
from app.engine.rule import match_rules
from app.models_business import BlacklistExtra, LoanApplication
from app.models_risk import RiskAssessment,RiskCase
from app.service.validator import validate_event

def process_event(db,event_type,source_id,user_id=None):
    validate_event(db,event_type,source_id)
    if event_type=="贷款申请": user_id,features=compute_loan_features(db,source_id)
    elif event_type=="转账": user_id,features=compute_transaction_features(db,source_id)
    elif event_type=="登录": user_id,features=compute_login_features(db,source_id)
    else: features=compute_user_features(db,user_id); features.update({"credit_card_apply":1})
    black=db.scalar(select(BlacklistExtra).where(BlacklistExtra.value.in_([user_id,source_id])))
    hits=match_rules(features); score=min(100,sum(x["score"] for x in hits)+(100 if black else 0))
    decision="拒绝" if score>=80 else "人工审核" if score>=50 else "关注" if score>=25 else "通过"
    aid=uuid.uuid4().hex[:16]; level="极高" if score>=80 else "高" if score>=50 else "中" if score>=25 else "低"
    row=RiskAssessment(assessment_id=aid,event_type=event_type,source_id=source_id,user_id=user_id,score=score,risk_level=level,decision=decision,hit_rules=json.dumps(hits,ensure_ascii=False),features=json.dumps(features,ensure_ascii=False),created_at=datetime.now())
    db.add(row)
    if decision in ("人工审核","拒绝"): db.add(RiskCase(case_id="C"+aid,assessment_id=aid,status="待审核",assignee="未分配",created_at=datetime.now()))
    db.commit(); return row

