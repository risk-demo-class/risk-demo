from pathlib import Path
import sys,hashlib,random
from datetime import datetime,timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from faker import Faker
from app.database import Base,SessionLocal,engine
from app.models_business import *

SEED=20260812; random.seed(SEED); fake=Faker("zh_CN"); Faker.seed(SEED)
def h(x): return hashlib.sha256(x.encode()).hexdigest()
def generate(n=160):
    Base.metadata.create_all(engine); db=SessionLocal(); now=datetime.now()
    for model in [BlacklistExtra,IpGeolocation,DeviceFingerprint,LoginLog,Transaction,LoanApplication,BankCard,UserInfo]: db.query(model).delete()
    ips=[]
    for i in range(60):
        ip=f"10.{i//255}.{i%255}.1"; ips.append(ip); db.add(IpGeolocation(ip=ip,country="中国",province=random.choice(["北京","上海","广东","境外"]),city=fake.city(),isp=random.choice(["电信","联通","云服务商"]),is_proxy=i%13==0,is_tor=i%29==0))
    for i in range(n):
        uid=f"U{i+1:04d}"; risky=i<35; score=random.randint(350,540) if risky else random.randint(600,820); reg=now-timedelta(days=random.randint(2,20) if risky else random.randint(60,1800)); income=random.randint(4000,45000)
        db.add(UserInfo(user_id=uid,name=fake.name(),id_card_hash=h("id"+uid),credit_score=score,register_at=reg,kyc_level=1 if risky and i%2==0 else random.randint(2,3),monthly_income=income))
        card=f"CARD{i+1:04d}"; db.add(BankCard(card_id=card,user_id=uid,card_no_hash=h(card),bank_code=random.choice(["ICBC","CCB","ABC","BOC"]),card_type=random.choice(["借记卡","信用卡"]),credit_limit=random.randint(10000,150000)))
        for d in range(5 if risky and i%3==0 else random.randint(1,2)):
            did=f"D{i+1:04d}{d}"; db.add(DeviceFingerprint(device_id=did,user_id=uid,fingerprint_hash=h(did),first_seen=reg,last_seen=now-timedelta(days=random.randint(0,20)),os=random.choice(["Windows","Android","iOS"]),browser=random.choice(["Chrome","Edge","Safari"])))
        for j in range(7 if risky else 2):
            fail=risky and j<6; db.add(LoginLog(login_id=f"LG{i+1:04d}{j}",user_id=uid,device_id=f"D{i+1:04d}0",ip=random.choice(ips),geo=random.choice(["北京","上海","境外"]),success=not fail,login_at=now-timedelta(hours=j)))
        debt=round(random.uniform(.68,.95),2) if risky else round(random.uniform(.05,.55),2); amount=income*random.uniform(14,24) if risky else income*random.uniform(2,9)
        db.add(LoanApplication(loan_id=f"L{i+1:04d}",user_id=uid,amount=round(amount,2),term_months=random.choice([6,12,24,36]),purpose=random.choice(["消费","经营","装修","教育"]),monthly_income=income,debt_ratio=debt,created_at=now-timedelta(days=random.randint(0,30))))
        amt=random.randint(60000,160000) if risky else random.randint(100,30000); hour=2 if risky else random.randint(7,22)
        db.add(Transaction(txn_id=f"T{i+1:04d}",from_card=card,to_card=f"OUT{i+1:04d}",amount=amt,channel=random.choice(["手机银行","网银","柜面"]),device_id=f"D{i+1:04d}0",ip=random.choice(ips),geo="境外" if risky else random.choice(["北京","上海","广东","浙江"]),created_at=now.replace(hour=hour,minute=0)))
    for i in range(8): db.add(BlacklistExtra(entry_id=f"B{i:03d}",type=random.choice(["设备指纹","IP","银行卡号","身份证号"]),value=f"blocked-{i}",reason="历史欺诈关联",expire_at=now+timedelta(days=365)))
    db.commit(); db.close(); print(f"造数完成：{n} 用户、{n} 贷款、{n} 转账、{n*2+35*5} 条以上登录记录")
if __name__=="__main__": generate()

