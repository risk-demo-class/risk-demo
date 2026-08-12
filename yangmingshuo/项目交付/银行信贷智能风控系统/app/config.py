import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/bank_risk.db")
BLACKLIST_TYPES = {"设备指纹", "IP", "银行卡号", "身份证号"}
EVENT_TYPES = {"信用卡申请", "贷款申请", "转账", "登录"}

