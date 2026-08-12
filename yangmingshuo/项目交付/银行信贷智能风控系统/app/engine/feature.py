from datetime import datetime, timedelta
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.models_business import BankCard, DeviceFingerprint, LoginLog, LoanApplication, Transaction, UserInfo

def compute_user_features(db: Session, user_id: str):
    user=db.get(UserInfo,user_id); now=datetime.now(); cards=db.scalars(select(BankCard.card_id).where(BankCard.user_id==user_id)).all()
    loan_count=db.scalar(select(func.count()).select_from(LoanApplication).where(LoanApplication.user_id==user_id)) or 0
    avg_debt=db.scalar(select(func.avg(LoanApplication.debt_ratio)).where(LoanApplication.user_id==user_id)) or 0
    fail_24h=db.scalar(select(func.count()).select_from(LoginLog).where(LoginLog.user_id==user_id,LoginLog.success==False,LoginLog.login_at>=now-timedelta(hours=24))) or 0
    device_count=db.scalar(select(func.count()).select_from(DeviceFingerprint).where(DeviceFingerprint.user_id==user_id)) or 0
    txn_24h=db.scalar(select(func.count()).select_from(Transaction).where(Transaction.from_card.in_(cards),Transaction.created_at>=now-timedelta(hours=24))) if cards else 0
    txn_amt=db.scalar(select(func.coalesce(func.sum(Transaction.amount),0)).where(Transaction.from_card.in_(cards),Transaction.created_at>=now-timedelta(hours=24))) if cards else 0
    return {"credit_score":user.credit_score if user else 0,"kyc_level":user.kyc_level if user else 0,"account_age_days":(now-user.register_at).days if user else 0,
            "loan_application_count":loan_count,"avg_debt_ratio":round(float(avg_debt),3),"login_fail_24h":fail_24h,"device_count":device_count,
            "txn_count_24h":txn_24h or 0,"txn_amount_24h":round(float(txn_amt or 0),2)}

def compute_loan_features(db: Session, source_id: str):
    x=db.get(LoanApplication,source_id); f=compute_user_features(db,x.user_id)
    f.update({"loan_amount":x.amount,"term_months":x.term_months,"debt_ratio":x.debt_ratio,"loan_income_multiple":round(x.amount/max(x.monthly_income,1),2)})
    return x.user_id,f

def compute_transaction_features(db: Session, source_id: str):
    x=db.get(Transaction,source_id); card=db.get(BankCard,x.from_card); f=compute_user_features(db,card.user_id)
    f.update({"txn_amount":x.amount,"night_transaction":int(x.created_at.hour<6),"cross_region":int(x.geo not in ("北京","上海","广东","浙江"))})
    return card.user_id,f

def compute_login_features(db: Session, source_id: str):
    x=db.get(LoginLog,source_id); f=compute_user_features(db,x.user_id); f.update({"login_success":int(x.success),"night_login":int(x.login_at.hour<6)})
    return x.user_id,f

