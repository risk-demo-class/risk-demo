from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.database import SessionLocal
from app.service.event import process_event
def main():
    db=SessionLocal()
    for event,sid in [("贷款申请","L0001"),("转账","T0001"),("登录","LG00010"),("贷款申请","L0100")]:
        x=process_event(db,event,sid); print(event,sid,"=>",x.score,x.risk_level,x.decision,x.hit_rules)
    db.close()
if __name__=="__main__": main()

