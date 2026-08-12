"""制造业业务表 SQLAlchemy 模型。

模型与 sql/init_business_tables.sql 一一对应；风险表位于独立的 risk SQL 文件中。
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Date, DateTime, DECIMAL, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Plant(Base):
    __tablename__ = "plant"
    plant_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    plant_name: Mapped[str] = mapped_column(String(100), nullable=False)
    workshop_name: Mapped[str] = mapped_column(String(100), nullable=False)
    line_name: Mapped[str] = mapped_column(String(100), nullable=False)
    area_code: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)


class Customer(Base):
    __tablename__ = "customer"
    customer_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    customer_name: Mapped[str] = mapped_column(String(100), nullable=False)
    customer_level: Mapped[str] = mapped_column(String(20), nullable=False)
    industry: Mapped[str] = mapped_column(String(50), nullable=False)
    credit_limit: Mapped[Decimal] = mapped_column(DECIMAL(14, 2), nullable=False)
    approved_status: Mapped[str] = mapped_column(String(20), nullable=False)


class Supplier(Base):
    __tablename__ = "supplier"
    supplier_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    supplier_name: Mapped[str] = mapped_column(String(100), nullable=False)
    supplier_level: Mapped[str] = mapped_column(String(20), nullable=False)
    qualification_status: Mapped[str] = mapped_column(String(20), nullable=False)
    qualification_expire_at: Mapped[date] = mapped_column(Date, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False)


class Employee(Base):
    __tablename__ = "employee"
    employee_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    employee_name: Mapped[str] = mapped_column(String(60), nullable=False)
    role_name: Mapped[str] = mapped_column(String(40), nullable=False)
    team_name: Mapped[str] = mapped_column(String(60), nullable=False)
    certification_type: Mapped[str | None] = mapped_column(String(60))
    certification_expire_at: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), nullable=False)


class Material(Base):
    __tablename__ = "material"
    material_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    material_name: Mapped[str] = mapped_column(String(100), nullable=False)
    material_type: Mapped[str] = mapped_column(String(20), nullable=False)
    specification: Mapped[str] = mapped_column(String(100), nullable=False)
    grade_name: Mapped[str] = mapped_column(String(60), nullable=False)
    uom: Mapped[str] = mapped_column(String(10), nullable=False)
    shelf_life_days: Mapped[int | None] = mapped_column(Integer)
    is_critical: Mapped[bool] = mapped_column(nullable=False)
    revision: Mapped[str] = mapped_column(String(20), nullable=False)


class Equipment(Base):
    __tablename__ = "equipment"
    equipment_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    plant_id: Mapped[str] = mapped_column(ForeignKey("plant.plant_id"), nullable=False)
    equipment_name: Mapped[str] = mapped_column(String(100), nullable=False)
    equipment_type: Mapped[str] = mapped_column(String(40), nullable=False)
    criticality: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    calibration_due_at: Mapped[date | None] = mapped_column(Date)
    maintenance_due_at: Mapped[date | None] = mapped_column(Date)


class Bom(Base):
    __tablename__ = "bom"
    bom_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    parent_material_id: Mapped[str] = mapped_column(ForeignKey("material.material_id"), nullable=False)
    component_material_id: Mapped[str] = mapped_column(ForeignKey("material.material_id"), nullable=False)
    qty_per: Mapped[Decimal] = mapped_column(DECIMAL(12, 4), nullable=False)
    scrap_rate: Mapped[Decimal] = mapped_column(DECIMAL(8, 4), nullable=False)
    revision: Mapped[str] = mapped_column(String(20), nullable=False)


class SalesOrder(Base):
    __tablename__ = "sales_order"
    sales_order_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customer.customer_id"), nullable=False)
    material_id: Mapped[str] = mapped_column(ForeignKey("material.material_id"), nullable=False)
    order_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    priority: Mapped[str] = mapped_column(String(20), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(DECIMAL(12, 2), nullable=False)
    revision: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class PurchaseOrder(Base):
    __tablename__ = "purchase_order"
    purchase_order_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    supplier_id: Mapped[str] = mapped_column(ForeignKey("supplier.supplier_id"), nullable=False)
    material_id: Mapped[str] = mapped_column(ForeignKey("material.material_id"), nullable=False)
    ordered_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(DECIMAL(12, 2), nullable=False)
    promise_date: Mapped[date] = mapped_column(Date, nullable=False)
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("employee.employee_id"))
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class Receipt(Base):
    __tablename__ = "receipt"
    receipt_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    purchase_order_id: Mapped[str] = mapped_column(ForeignKey("purchase_order.purchase_order_id"), nullable=False)
    supplier_lot_no: Mapped[str] = mapped_column(String(40), nullable=False)
    received_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    warehouse_id: Mapped[str] = mapped_column(String(20), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    receiver_id: Mapped[str] = mapped_column(ForeignKey("employee.employee_id"), nullable=False)


class IqcInspection(Base):
    __tablename__ = "iqc_inspection"
    iqc_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    receipt_id: Mapped[str] = mapped_column(ForeignKey("receipt.receipt_id"), nullable=False)
    inspection_status: Mapped[str] = mapped_column(String(20), nullable=False)
    sample_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    defect_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    inspector_id: Mapped[str] = mapped_column(ForeignKey("employee.employee_id"), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)


class Inventory(Base):
    __tablename__ = "inventory"
    inventory_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    material_id: Mapped[str] = mapped_column(ForeignKey("material.material_id"), nullable=False)
    lot_no: Mapped[str] = mapped_column(String(40), nullable=False)
    warehouse_id: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    quality_status: Mapped[str] = mapped_column(String(20), nullable=False)
    received_at: Mapped[date] = mapped_column(Date, nullable=False)
    expiry_date: Mapped[date | None] = mapped_column(Date)


class WorkOrder(Base):
    __tablename__ = "work_order"
    work_order_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    sales_order_id: Mapped[str | None] = mapped_column(ForeignKey("sales_order.sales_order_id"))
    plant_id: Mapped[str] = mapped_column(ForeignKey("plant.plant_id"), nullable=False)
    material_id: Mapped[str] = mapped_column(ForeignKey("material.material_id"), nullable=False)
    planned_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    completed_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    bom_revision: Mapped[str] = mapped_column(String(20), nullable=False)
    routing_revision: Mapped[str] = mapped_column(String(20), nullable=False)
    planned_start_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    planned_end_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)


class MaterialIssue(Base):
    __tablename__ = "material_issue"
    issue_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    work_order_id: Mapped[str] = mapped_column(ForeignKey("work_order.work_order_id"), nullable=False)
    material_id: Mapped[str] = mapped_column(ForeignKey("material.material_id"), nullable=False)
    lot_no: Mapped[str] = mapped_column(String(40), nullable=False)
    issue_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    issued_by: Mapped[str] = mapped_column(ForeignKey("employee.employee_id"), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class OperationReport(Base):
    __tablename__ = "operation_report"
    operation_report_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    work_order_id: Mapped[str] = mapped_column(ForeignKey("work_order.work_order_id"), nullable=False)
    operation_seq: Mapped[int] = mapped_column(Integer, nullable=False)
    good_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    scrap_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    labor_hours: Mapped[Decimal] = mapped_column(DECIMAL(8, 2), nullable=False)
    operator_id: Mapped[str] = mapped_column(ForeignKey("employee.employee_id"), nullable=False)
    reported_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class IpqcInspection(Base):
    __tablename__ = "ipqc_inspection"
    ipqc_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    work_order_id: Mapped[str] = mapped_column(ForeignKey("work_order.work_order_id"), nullable=False)
    operation_seq: Mapped[int] = mapped_column(Integer, nullable=False)
    measured_value: Mapped[Decimal] = mapped_column(DECIMAL(12, 4), nullable=False)
    lsl: Mapped[Decimal] = mapped_column(DECIMAL(12, 4), nullable=False)
    usl: Mapped[Decimal] = mapped_column(DECIMAL(12, 4), nullable=False)
    result: Mapped[str] = mapped_column(String(20), nullable=False)
    inspector_id: Mapped[str] = mapped_column(ForeignKey("employee.employee_id"), nullable=False)
    equipment_id: Mapped[str] = mapped_column(ForeignKey("equipment.equipment_id"), nullable=False)
    inspected_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class FinishedGoods(Base):
    __tablename__ = "finished_goods"
    completion_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    work_order_id: Mapped[str] = mapped_column(ForeignKey("work_order.work_order_id"), nullable=False)
    lot_no: Mapped[str] = mapped_column(String(40), nullable=False)
    serial_range: Mapped[str | None] = mapped_column(String(100))
    good_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    quality_status: Mapped[str] = mapped_column(String(20), nullable=False)
    warehouse_id: Mapped[str] = mapped_column(String(20), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class Shipment(Base):
    __tablename__ = "shipment"
    shipment_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customer.customer_id"), nullable=False)
    sales_order_id: Mapped[str] = mapped_column(ForeignKey("sales_order.sales_order_id"), nullable=False)
    material_id: Mapped[str] = mapped_column(ForeignKey("material.material_id"), nullable=False)
    lot_no: Mapped[str] = mapped_column(String(40), nullable=False)
    ship_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    quality_status: Mapped[str] = mapped_column(String(20), nullable=False)
    released_by: Mapped[str | None] = mapped_column(ForeignKey("employee.employee_id"))
    ship_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class CustomerComplaint(Base):
    __tablename__ = "customer_complaint"
    complaint_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customer.customer_id"), nullable=False)
    shipment_id: Mapped[str | None] = mapped_column(ForeignKey("shipment.shipment_id"))
    defect_code: Mapped[str] = mapped_column(String(40), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    claim_amount: Mapped[Decimal] = mapped_column(DECIMAL(12, 2), nullable=False)
    returned_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class MaintenanceOrder(Base):
    __tablename__ = "maintenance_order"
    maintenance_order_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    equipment_id: Mapped[str] = mapped_column(ForeignKey("equipment.equipment_id"), nullable=False)
    failure_code: Mapped[str] = mapped_column(String(40), nullable=False)
    downtime_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    technician_id: Mapped[str] = mapped_column(ForeignKey("employee.employee_id"), nullable=False)
    loto_required: Mapped[bool] = mapped_column(nullable=False)
    acceptance_status: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)


class BusinessEvent(Base):
    __tablename__ = "business_event"
    event_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(40), nullable=False)
    source_system: Mapped[str] = mapped_column(String(20), nullable=False)
    operator_id: Mapped[str | None] = mapped_column(ForeignKey("employee.employee_id"))
    business_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    trace_id: Mapped[str] = mapped_column(String(40), nullable=False)
    payload_json: Mapped[dict | None] = mapped_column(JSON)
