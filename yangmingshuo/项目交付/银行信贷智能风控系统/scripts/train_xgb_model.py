from pathlib import Path
import sys,joblib
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from sqlalchemy import select
from sklearn.metrics import f1_score,roc_auc_score
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier
from app.database import SessionLocal
from app.models_business import LoanApplication,UserInfo
FEATURES=["credit_score","kyc_level","account_age_days","amount","debt_ratio","income_multiple"]
def main():
    db=SessionLocal(); rows=db.execute(select(LoanApplication,UserInfo).join(UserInfo,LoanApplication.user_id==UserInfo.user_id)).all(); X=[]; y=[]
    for loan,user in rows:
        X.append([user.credit_score,user.kyc_level,(loan.created_at-user.register_at).days,loan.amount,loan.debt_ratio,loan.amount/max(loan.monthly_income,1)])
        y.append(int(user.credit_score<560 or loan.debt_ratio>.68 or loan.amount/max(loan.monthly_income,1)>13))
    X=np.asarray(X); y=np.asarray(y); a,b,c,d=train_test_split(X,y,test_size=.25,random_state=42,stratify=y)
    model=XGBClassifier(n_estimators=100,max_depth=3,learning_rate=.08,subsample=.85,colsample_bytree=.85,eval_metric="logloss",random_state=42); model.fit(a,c)
    prob=model.predict_proba(b)[:,1]; pred=(prob>=.5).astype(int); Path("models").mkdir(exist_ok=True); joblib.dump({"model":model,"features":FEATURES},"models/credit_risk_xgb.joblib")
    print(f"val_auc={roc_auc_score(d,prob):.4f}"); print(f"val_f1={f1_score(d,pred):.4f}"); db.close()
if __name__=="__main__": main()

