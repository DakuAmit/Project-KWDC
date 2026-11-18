from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Numeric, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base

class Warehouse(Base):
    __tablename__ = "warehouses"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    location = Column(String(255), nullable=False)
    address = Column(Text, nullable=True)
    latitude = Column(Numeric(10, 8), nullable=True)
    longitude = Column(Numeric(11, 8), nullable=True)
    contact_number = Column(String(50), nullable=True)
    email = Column(String(255), nullable=True)
    area_sqft = Column(Numeric(12, 2), nullable=True)
    area_sqm = Column(Numeric(12, 2), nullable=True)
    price_per_sqft = Column(Numeric(12, 2), nullable=True)
    description = Column(Text, nullable=True)
    
    # Security
    cctv_count = Column(Integer, default=0)
    guards_count = Column(Integer, default=0)
    fire_extinguishers = Column(Integer, default=0)
    cctv_stream_urls = Column(Text, nullable=True)
    
    # Facilities nearby
    nearby_police = Column(String(255), nullable=True)
    nearby_fire = Column(String(255), nullable=True)
    nearby_hospital = Column(String(255), nullable=True)
    nearby_bank = Column(String(255), nullable=True)
    nearby_fuel = Column(String(255), nullable=True)
    nearby_market = Column(String(255), nullable=True)
    
    # Cold storage
    cold_storage = Column(Boolean, default=False)
    temperature_min = Column(Numeric(5, 2), nullable=True)
    temperature_max = Column(Numeric(5, 2), nullable=True)
    humidity_control = Column(Boolean, default=False)
    
    # Kataho fields
    kataho_code = Column(String(100), nullable=True)
    grid_id = Column(String(100), nullable=True)
    city = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    postal_code = Column(String(50), nullable=True)
    country = Column(String(100), default="Nepal")
    
    # Additional features
    insurance_available = Column(Boolean, default=False)
    loading_dock = Column(Boolean, default=False)
    office_space = Column(Boolean, default=False)
    staff_quarters = Column(Boolean, default=False)
    parking_spaces = Column(Integer, default=0)
    parking_type = Column(String(50), default="open")
    available_from = Column(DateTime, nullable=True)
    minimum_rental_period = Column(Integer, default=1)
    special_notes = Column(Text, nullable=True)
    facilities = Column(Text, nullable=True)
    
    # Media
    front_image = Column(String(255), nullable=True)
    interior_image = Column(String(255), nullable=True)
    exterior_image = Column(String(255), nullable=True)
    
    # Status
    status = Column(String(50), default="pending", index=True)
    approved_at = Column(DateTime, nullable=True)
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    rejection_reason = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    owner = relationship("User", foreign_keys=[user_id], back_populates="warehouses")
    requests = relationship("WarehouseRequest", back_populates="warehouse", cascade="all, delete-orphan")
    photos = relationship("WarehousePhoto", back_populates="warehouse", cascade="all, delete-orphan")
    documents = relationship("WarehouseDocument", back_populates="warehouse", cascade="all, delete-orphan")
    stocks = relationship("Stock", back_populates="warehouse")
    boxes = relationship("Box", back_populates="warehouse")

class WarehousePhoto(Base):
    __tablename__ = "warehouse_photos"

    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False)
    photo_path = Column(String(255), nullable=False)
    photo_type = Column(String(50), nullable=True)
    is_primary = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    warehouse = relationship("Warehouse", back_populates="photos")

class WarehouseDocument(Base):
    __tablename__ = "warehouse_documents"

    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False)
    document_path = Column(String(255), nullable=False)
    document_type = Column(String(100), nullable=False)
    document_name = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    warehouse = relationship("Warehouse", back_populates="documents")

class WarehouseRequest(Base):
    __tablename__ = "warehouse_requests"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False, index=True)
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    space_required = Column(Numeric(12, 2), nullable=True)
    purpose = Column(Text, nullable=True)
    status = Column(String(50), default="pending", index=True)
    approved_at = Column(DateTime, nullable=True)
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    admin_notes = Column(Text, nullable=True)
    preferred_warehouse = Column(String(255), nullable=True)
    equipment_type = Column(String(100), nullable=True)
    agreed_price = Column(Numeric(12, 2), nullable=True)
    pricing_details = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    client = relationship("User", foreign_keys=[client_id])
    warehouse = relationship("Warehouse", back_populates="requests")
    invoices = relationship("Invoice", back_populates="warehouse_request")
