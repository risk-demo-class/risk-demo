"""物流寄递风控业务表；核心风控表仍由 models_risk.py 提供。"""
from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import DateTime, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, synonym
from app.database import Base

class UserInfo(Base):
    __tablename__="user_info"
    user_id: Mapped[str]=mapped_column(String(50),primary_key=True)
    name: Mapped[str]=mapped_column(String(50),nullable=False)
    id_type: Mapped[str]=mapped_column(String(20),default="身份证")
    id_number_hash: Mapped[str]=mapped_column(String(128),nullable=False,index=True)
    phone: Mapped[str]=mapped_column(String(30),nullable=False,index=True)
    real_name_status: Mapped[int]=mapped_column(Integer,default=1)
    account_type: Mapped[str]=mapped_column(String(20),default="个人")
    register_time: Mapped[datetime]=mapped_column(DateTime,nullable=False)
    device_id: Mapped[Optional[str]]=mapped_column(String(64),index=True)
    usual_city: Mapped[Optional[str]]=mapped_column(String(50))

class Address(Base):
    __tablename__="address"
    address_id: Mapped[str]=mapped_column(String(50),primary_key=True)
    user_id: Mapped[Optional[str]]=mapped_column(String(50),index=True)
    contact_name: Mapped[str]=mapped_column(String(50),nullable=False)
    contact_phone: Mapped[str]=mapped_column(String(30),nullable=False,index=True)
    id_number_hash: Mapped[Optional[str]]=mapped_column(String(128),index=True)
    country: Mapped[str]=mapped_column(String(50),default="中国")
    province: Mapped[str]=mapped_column(String(50),nullable=False)
    city: Mapped[str]=mapped_column(String(50),nullable=False)
    district: Mapped[str]=mapped_column(String(50),nullable=False)
    detail_address: Mapped[str]=mapped_column(String(255),nullable=False)
    address_type: Mapped[str]=mapped_column(String(20),default="固定地址")
    is_remote_area: Mapped[int]=mapped_column(Integer,default=0)
    create_time: Mapped[datetime]=mapped_column(DateTime,nullable=False)
    receive_id=synonym("address_id")
    receiver_phone=synonym("contact_phone")

class Shipment(Base):
    __tablename__="shipment"
    shipment_id: Mapped[str]=mapped_column(String(50),primary_key=True)
    sender_user_id: Mapped[str]=mapped_column(String(50),nullable=False,index=True)
    sender_address_id: Mapped[str]=mapped_column(String(50),nullable=False,index=True)
    receiver_address_id: Mapped[str]=mapped_column(String(50),nullable=False,index=True)
    shipment_type: Mapped[str]=mapped_column(String(20),default="普通件")
    payment_type: Mapped[str]=mapped_column(String(20),default="寄付")
    cod_amount: Mapped[Decimal]=mapped_column(Numeric(12,2),default=0)
    declared_value: Mapped[Decimal]=mapped_column(Numeric(12,2),default=0)
    actual_weight: Mapped[Decimal]=mapped_column(Numeric(10,3),default=0)
    declared_weight: Mapped[Decimal]=mapped_column(Numeric(10,3),default=0)
    destination_country: Mapped[str]=mapped_column(String(50),default="中国")
    is_cross_border: Mapped[int]=mapped_column(Integer,default=0)
    create_time: Mapped[datetime]=mapped_column(DateTime,nullable=False,index=True)
    shipment_status: Mapped[str]=mapped_column(String(20),default="已创建")
    device_id: Mapped[Optional[str]]=mapped_column(String(64),index=True)
    order_id=synonym("shipment_id")
    user_id=synonym("sender_user_id")
    receive_id=synonym("receiver_address_id")

class ShipmentItem(Base):
    __tablename__="shipment_item"
    item_id: Mapped[str]=mapped_column(String(50),primary_key=True)
    shipment_id: Mapped[str]=mapped_column(String(50),nullable=False,index=True)
    item_name: Mapped[str]=mapped_column(String(100),nullable=False)
    item_category: Mapped[str]=mapped_column(String(50),nullable=False)
    quantity: Mapped[int]=mapped_column(Integer,default=1)
    declared_dangerous: Mapped[int]=mapped_column(Integer,default=0)
    battery_flag: Mapped[int]=mapped_column(Integer,default=0)
    chemical_flag: Mapped[int]=mapped_column(Integer,default=0)
    liquid_flag: Mapped[int]=mapped_column(Integer,default=0)
    security_check_result: Mapped[str]=mapped_column(String(30),default="通过")

class CustomsDeclaration(Base):
    __tablename__="customs_declaration"
    declaration_id: Mapped[str]=mapped_column(String(50),primary_key=True)
    shipment_id: Mapped[str]=mapped_column(String(50),nullable=False,unique=True,index=True)
    customs_code: Mapped[str]=mapped_column(String(30),nullable=False)
    declared_item_name: Mapped[str]=mapped_column(String(100),nullable=False)
    declared_quantity: Mapped[int]=mapped_column(Integer,default=1)
    declared_value: Mapped[Decimal]=mapped_column(Numeric(12,2),default=0)
    declared_weight: Mapped[Decimal]=mapped_column(Numeric(10,3),default=0)
    currency: Mapped[str]=mapped_column(String(10),default="CNY")
    origin_country: Mapped[str]=mapped_column(String(50),default="中国")
    destination_country: Mapped[str]=mapped_column(String(50),nullable=False)
    declaration_time: Mapped[datetime]=mapped_column(DateTime,nullable=False)
    inspection_result: Mapped[Optional[str]]=mapped_column(String(50))

class DeliveryResult(Base):
    __tablename__="delivery_result"
    delivery_id: Mapped[str]=mapped_column(String(50),primary_key=True)
    shipment_id: Mapped[str]=mapped_column(String(50),nullable=False,index=True)
    delivery_status: Mapped[str]=mapped_column(String(20),nullable=False,index=True)
    receiver_name: Mapped[str]=mapped_column(String(50),nullable=False)
    receiver_phone: Mapped[str]=mapped_column(String(30),nullable=False)
    refuse_reason: Mapped[Optional[str]]=mapped_column(String(255))
    delivery_time: Mapped[datetime]=mapped_column(DateTime,nullable=False)
    cod_amount: Mapped[Decimal]=mapped_column(Numeric(12,2),default=0)
    cod_received: Mapped[int]=mapped_column(Integer,default=0)
    courier_id: Mapped[Optional[str]]=mapped_column(String(50))

class BlacklistExtra(Base):
    __tablename__="blacklist_extra"
    entry_id: Mapped[int]=mapped_column(Integer,primary_key=True,autoincrement=True)
    type: Mapped[str]=mapped_column(String(30),nullable=False)
    value: Mapped[str]=mapped_column(String(255),nullable=False,index=True)
    reason: Mapped[Optional[str]]=mapped_column(Text)
    expire_at: Mapped[Optional[datetime]]=mapped_column(DateTime)
    source: Mapped[str]=mapped_column(String(50),default="物流业务")

OrderInfo=Shipment
ReceiveInfo=Address
OrderDetail=ShipmentItem
