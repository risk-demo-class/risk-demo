from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class UserInfo(Base):
    __tablename__="user_info"
    user_id: Mapped[str]=mapped_column(String(32),primary_key=True)
    name: Mapped[str]=mapped_column(String(40)); id_card_hash: Mapped[str]=mapped_column(String(64),unique=True,index=True)
    credit_score: Mapped[int]=mapped_column(Integer,index=True); register_at: Mapped[datetime]=mapped_column(DateTime,index=True)
    kyc_level: Mapped[int]=mapped_column(Integer); monthly_income: Mapped[float]=mapped_column(Float,default=0)

class BankCard(Base):
    __tablename__="bank_card"
    card_id: Mapped[str]=mapped_column(String(32),primary_key=True); user_id: Mapped[str]=mapped_column(ForeignKey("user_info.user_id"),index=True)
    card_no_hash: Mapped[str]=mapped_column(String(64),unique=True,index=True); bank_code: Mapped[str]=mapped_column(String(20))
    card_type: Mapped[str]=mapped_column(String(16)); credit_limit: Mapped[float]=mapped_column(Float,default=0)

class Transaction(Base):
    __tablename__="bank_transaction"
    txn_id: Mapped[str]=mapped_column(String(32),primary_key=True); from_card: Mapped[str]=mapped_column(String(32),index=True)
    to_card: Mapped[str]=mapped_column(String(32),index=True); amount: Mapped[float]=mapped_column(Float,index=True)
    channel: Mapped[str]=mapped_column(String(20)); device_id: Mapped[str]=mapped_column(String(32),index=True)
    ip: Mapped[str]=mapped_column(String(45),index=True); geo: Mapped[str]=mapped_column(String(40)); created_at: Mapped[datetime]=mapped_column(DateTime,index=True)

class LoanApplication(Base):
    __tablename__="loan_application"
    loan_id: Mapped[str]=mapped_column(String(32),primary_key=True); user_id: Mapped[str]=mapped_column(ForeignKey("user_info.user_id"),index=True)
    amount: Mapped[float]=mapped_column(Float); term_months: Mapped[int]=mapped_column(Integer); purpose: Mapped[str]=mapped_column(String(40))
    monthly_income: Mapped[float]=mapped_column(Float); debt_ratio: Mapped[float]=mapped_column(Float,index=True); created_at: Mapped[datetime]=mapped_column(DateTime)

class LoginLog(Base):
    __tablename__="login_log"
    login_id: Mapped[str]=mapped_column(String(32),primary_key=True); user_id: Mapped[str]=mapped_column(ForeignKey("user_info.user_id"),index=True)
    device_id: Mapped[str]=mapped_column(String(32),index=True); ip: Mapped[str]=mapped_column(String(45),index=True); geo: Mapped[str]=mapped_column(String(40))
    success: Mapped[bool]=mapped_column(Boolean,index=True); login_at: Mapped[datetime]=mapped_column(DateTime,index=True)

class DeviceFingerprint(Base):
    __tablename__="device_fingerprint"
    device_id: Mapped[str]=mapped_column(String(32),primary_key=True); user_id: Mapped[str]=mapped_column(ForeignKey("user_info.user_id"),index=True)
    fingerprint_hash: Mapped[str]=mapped_column(String(64),index=True); first_seen: Mapped[datetime]=mapped_column(DateTime); last_seen: Mapped[datetime]=mapped_column(DateTime,index=True)
    os: Mapped[str]=mapped_column(String(20)); browser: Mapped[str]=mapped_column(String(20))

class IpGeolocation(Base):
    __tablename__="ip_geolocation"
    ip: Mapped[str]=mapped_column(String(45),primary_key=True); country: Mapped[str]=mapped_column(String(30)); province: Mapped[str]=mapped_column(String(30))
    city: Mapped[str]=mapped_column(String(30)); isp: Mapped[str]=mapped_column(String(40)); is_proxy: Mapped[bool]=mapped_column(Boolean,index=True); is_tor: Mapped[bool]=mapped_column(Boolean,index=True)

class BlacklistExtra(Base):
    __tablename__="blacklist_extra"
    entry_id: Mapped[str]=mapped_column(String(32),primary_key=True); type: Mapped[str]=mapped_column(String(20),index=True)
    value: Mapped[str]=mapped_column(String(80),index=True); reason: Mapped[str]=mapped_column(String(200)); expire_at: Mapped[datetime|None]=mapped_column(DateTime,nullable=True)

