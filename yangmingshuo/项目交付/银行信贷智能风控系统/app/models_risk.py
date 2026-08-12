from datetime import datetime
from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class RiskAssessment(Base):
    __tablename__="risk_assessment"
    assessment_id: Mapped[str]=mapped_column(String(32),primary_key=True); event_type: Mapped[str]=mapped_column(String(20),index=True)
    source_id: Mapped[str]=mapped_column(String(32),index=True); user_id: Mapped[str]=mapped_column(String(32),index=True)
    score: Mapped[float]=mapped_column(Float,index=True); risk_level: Mapped[str]=mapped_column(String(10)); decision: Mapped[str]=mapped_column(String(20),index=True)
    hit_rules: Mapped[str]=mapped_column(Text); features: Mapped[str]=mapped_column(Text); created_at: Mapped[datetime]=mapped_column(DateTime,index=True)

class RiskCase(Base):
    __tablename__="risk_case"
    case_id: Mapped[str]=mapped_column(String(32),primary_key=True); assessment_id: Mapped[str]=mapped_column(String(32),index=True)
    status: Mapped[str]=mapped_column(String(20),default="待审核"); assignee: Mapped[str]=mapped_column(String(40),default="未分配"); created_at: Mapped[datetime]=mapped_column(DateTime)

