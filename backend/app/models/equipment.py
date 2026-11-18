from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, Numeric, ForeignKey, Date
from sqlalchemy.orm import relationship
from app.core.database import Base

class Equipment(Base):
    __tablename__ = "equipment"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    name = Column(String(255), nullable=False)
    type = Column(String(100), nullable=False)  # forklift, crane, pallet_jack, loader
    model = Column(String(100), nullable=True)
    year = Column(Integer, nullable=True)
    description = Column(Text, nullable=True)
    
    # Specs
    weight = Column(Numeric(10, 2), nullable=True)
    engine_power = Column(Numeric(10, 2), nullable=True)
    bucket_capacity = Column(Numeric(10, 2), nullable=True)
    max_reach = Column(Numeric(10, 2), nullable=True)
    
    # Pricing
    daily_rate = Column(Numeric(10, 2), nullable=True)
    weekly_rate = Column(Numeric(10, 2), nullable=True)
    monthly_rate = Column(Numeric(10, 2), nullable=True)
    security_deposit = Column(Numeric(10, 2), nullable=True)
    
    location = Column(String(255), nullable=True)
    status = Column(String(50), default="available", index=True)  # available, rented, maintenance
    
    front_photo = Column(String(255), nullable=True)
    side_photo = Column(String(255), nullable=True)
    working_photo = Column(String(255), nullable=True)
    registration_doc = Column(String(255), nullable=True)
    insurance_doc = Column(String(255), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("User", foreign_keys=[owner_id])
    jobs = relationship("EquipmentJob", back_populates="equipment")

class EquipmentJob(Base):
    __tablename__ = "equipment_jobs"

    id = Column(Integer, primary_key=True, index=True)
    equipment_id = Column(Integer, ForeignKey("equipment.id"), nullable=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    client_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    job_type = Column(String(100), nullable=True)
    pickup_location = Column(Text, nullable=True)
    delivery_location = Column(Text, nullable=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    description = Column(Text, nullable=True)
    location = Column(String(255), nullable=True)
    
    price = Column(Numeric(10, 2), default=0.0)
    proposed_price = Column(Numeric(10, 2), nullable=True)
    amount = Column(Numeric(10, 2), default=0.0)
    paid_amount = Column(Numeric(10, 2), default=0.0)
    client_counter_price = Column(Numeric(10, 2), nullable=True)
    
    proposal_message = Column(Text, nullable=True)
    client_message = Column(Text, nullable=True)
    
    status = Column(String(50), default="pending", index=True)  # pending, approved, in_progress, completed, cancelled
    accepted_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    equipment = relationship("Equipment", back_populates="jobs")
    client = relationship("User", foreign_keys=[client_id])
    owner = relationship("User", foreign_keys=[owner_id])

class EquipmentRequest(Base):
    __tablename__ = "equipment_requests"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    equipment_id = Column(Integer, ForeignKey("equipment.id"), nullable=True)
    equipment_type = Column(String(100), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    location = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(50), default="pending", index=True)
    quoted_price = Column(Numeric(10, 2), nullable=True)
    assigned_equipment_id = Column(Integer, ForeignKey("equipment.id"), nullable=True)
    special_requirements = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    client = relationship("User", foreign_keys=[client_id])
