from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Numeric, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    user_code = Column(String(50), unique=True, index=True, nullable=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    email_verified_at = Column(DateTime, nullable=True)
    password = Column(String(255), nullable=False)
    phone = Column(String(50), nullable=True)
    role = Column(String(50), default="client", index=True)
    is_active = Column(Boolean, default=True)
    avg_rating = Column(Numeric(3, 1), default=0.0)
    address = Column(Text, nullable=True)
    profile_photo = Column(String(255), nullable=True)
    is_admin = Column(Boolean, default=False)
    is_driver = Column(Boolean, default=False)
    is_equipment_owner = Column(Boolean, default=False)
    is_property_owner = Column(Boolean, default=False)
    user_type = Column(String(50), nullable=True)
    preferred_location = Column(Text, nullable=True)
    two_factor_secret = Column(String(255), nullable=True)
    two_factor_confirmed = Column(Boolean, default=False)
    date_of_birth = Column(DateTime, nullable=True)
    email_verification_token = Column(String(255), nullable=True)
    reset_password_token = Column(String(255), nullable=True)
    reset_password_expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    contacts = relationship("UserContact", back_populates="user", cascade="all, delete-orphan")
    reminders = relationship("UserReminder", back_populates="user", cascade="all, delete-orphan")
    warehouses = relationship("Warehouse", back_populates="owner", foreign_keys="Warehouse.user_id")
    vehicles = relationship("Vehicle", back_populates="driver", foreign_keys="Vehicle.driver_id")
    dispatch_orders_as_client = relationship("DispatchOrder", back_populates="client", foreign_keys="DispatchOrder.client_id")
    dispatch_orders_as_driver = relationship("DispatchOrder", back_populates="driver", foreign_keys="DispatchOrder.driver_id")
    invoices = relationship("Invoice", back_populates="user", foreign_keys="Invoice.user_id")

class UserContact(Base):
    __tablename__ = "user_contacts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    relationship_type = Column(String(100), nullable=True)
    is_primary = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="contacts")

class UserReminder(Base):
    __tablename__ = "user_reminders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    reminder_date = Column(DateTime, nullable=False)
    is_completed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="reminders")
