from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, Date
from sqlalchemy.orm import relationship
from app.core.database import Base

class SecurityAgency(Base):
    __tablename__ = "security_agencies"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    agency_name = Column(String(255), nullable=False)
    registration_number = Column(String(100), nullable=True)
    license_number = Column(String(100), nullable=True)
    address = Column(Text, nullable=False)
    phone = Column(String(50), nullable=True)
    emergency_phone = Column(String(50), nullable=True)
    email = Column(String(255), nullable=True)
    services_offered = Column(Text, nullable=True)
    year_established = Column(String(50), nullable=True)
    pan_vat_number = Column(String(50), nullable=True)
    certifications = Column(Text, nullable=True)
    logo = Column(String(255), nullable=True)
    status = Column(String(50), default="pending", index=True)  # pending, approved, suspended
    approved_at = Column(DateTime, nullable=True)
    is_verified = Column(Boolean, default=False)
    admin_notes = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User")
    personnel = relationship("SecurityPersonnel", back_populates="agency", cascade="all, delete-orphan")
    assignments = relationship("SecurityAssignment", back_populates="agency", cascade="all, delete-orphan")
    incidents = relationship("SecurityIncident", back_populates="agency", cascade="all, delete-orphan")

class SecurityPersonnel(Base):
    __tablename__ = "security_personnel"

    id = Column(Integer, primary_key=True, index=True)
    security_agency_id = Column(Integer, ForeignKey("security_agencies.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    phone = Column(String(50), nullable=True)
    citizenship_no = Column(String(100), nullable=True)
    badge_id = Column(String(100), nullable=True)
    rank = Column(String(100), default="Guard")
    status = Column(String(50), default="available", index=True)  # available, assigned, on_leave
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    agency = relationship("SecurityAgency", back_populates="personnel")

class SecurityAssignment(Base):
    __tablename__ = "security_assignments"

    id = Column(Integer, primary_key=True, index=True)
    security_agency_id = Column(Integer, ForeignKey("security_agencies.id", ondelete="CASCADE"), nullable=False)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    personnel_id = Column(Integer, ForeignKey("security_personnel.id"), nullable=True)
    shift_type = Column(String(50), default="day")  # day, night, 24h
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    status = Column(String(50), default="active", index=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    agency = relationship("SecurityAgency", back_populates="assignments")
    warehouse = relationship("Warehouse")

class SecurityIncident(Base):
    __tablename__ = "security_incidents"

    id = Column(Integer, primary_key=True, index=True)
    security_agency_id = Column(Integer, ForeignKey("security_agencies.id", ondelete="CASCADE"), nullable=False)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=True)
    incident_type = Column(String(100), nullable=False)  # theft, fire, unauthorized_entry, damage
    severity = Column(String(50), default="low")  # low, medium, high, critical
    description = Column(Text, nullable=False)
    police_station_notified = Column(String(255), nullable=True)
    status = Column(String(50), default="reported", index=True)  # reported, investigating, resolved
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    agency = relationship("SecurityAgency", back_populates="incidents")
    warehouse = relationship("Warehouse")
