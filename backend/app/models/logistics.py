from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Numeric, ForeignKey, Date
from sqlalchemy.orm import relationship
from app.core.database import Base

class Vehicle(Base):
    __tablename__ = "vehicles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    driver_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    driver_code = Column(String(50), nullable=True)
    vehicle_number = Column(String(100), nullable=False)
    vehicle_type = Column(String(50), nullable=False)
    custom_vehicle_type = Column(String(100), nullable=True)
    capacity = Column(Numeric(10, 2), default=0.0)
    capacity_unit = Column(String(20), default="tons")
    manufacturer = Column(String(100), nullable=True)
    model = Column(String(100), nullable=True)
    year = Column(Integer, nullable=True)
    color = Column(String(50), nullable=True)
    fuel_type = Column(String(50), nullable=True)
    registration_number = Column(String(100), nullable=True)
    blue_book_file_path = Column(String(255), nullable=True)
    status = Column(String(50), default="pending", index=True)
    is_verified = Column(Boolean, default=False)
    verified_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    verified_at = Column(DateTime, nullable=True)
    rejection_reason = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    driver = relationship("User", foreign_keys=[driver_id], back_populates="vehicles")

class DriverRate(Base):
    __tablename__ = "driver_rates"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    driver_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    date = Column(Date, nullable=False, index=True)
    rate_tiers = Column(Text, nullable=True)  # JSON encoded rate tiers
    base_price = Column(Numeric(10, 2), default=0.0)
    vehicle_type = Column(String(50), default="Standard")
    status = Column(String(50), default="active", index=True)
    is_active = Column(Boolean, default=True)
    valid_until = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class DispatchOrder(Base):
    __tablename__ = "dispatch_orders"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    driver_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=True)
    warehouse_request_id = Column(Integer, ForeignKey("warehouse_requests.id"), nullable=True)
    driver_rate_id = Column(Integer, ForeignKey("driver_rates.id"), nullable=True)
    
    tracking_id = Column(String(100), unique=True, index=True, nullable=True)
    invoice_no = Column(String(100), unique=True, nullable=True)
    pickup_address = Column(Text, nullable=False)
    pickup_latitude = Column(Numeric(10, 8), nullable=True)
    pickup_longitude = Column(Numeric(11, 8), nullable=True)
    pickup_contact_person = Column(String(255), nullable=True)
    pickup_contact_phone = Column(String(50), nullable=True)
    
    total_distance = Column(Numeric(10, 2), default=0.0)
    base_price = Column(Numeric(12, 2), default=0.0)
    driver_earning = Column(Numeric(12, 2), nullable=True)
    admin_margin = Column(Numeric(12, 2), nullable=True)
    tax_amount = Column(Numeric(10, 2), default=0.0)
    grand_total = Column(Numeric(10, 2), default=0.0)
    
    bill_type = Column(String(50), default="regular")
    pan_number = Column(String(50), nullable=True)
    payment_status = Column(String(50), default="pending")
    payment_due_date = Column(DateTime, nullable=True)
    payment_date = Column(DateTime, nullable=True)
    
    status = Column(String(50), default="pending", index=True)  # pending, assigned, picked_up, on_the_way, delivered, cancelled
    assigned_at = Column(DateTime, nullable=True)
    picked_up_at = Column(DateTime, nullable=True)
    on_the_way_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    
    client_rating = Column(Integer, nullable=True)
    client_feedback = Column(Text, nullable=True)
    
    current_latitude = Column(Numeric(10, 8), nullable=True)
    current_longitude = Column(Numeric(11, 8), nullable=True)
    last_location_update = Column(DateTime, nullable=True)
    tracking_enabled = Column(Boolean, default=False)
    tracking_token = Column(String(100), nullable=True)
    total_boxes = Column(Integer, default=0)
    admin_notes = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    client = relationship("User", foreign_keys=[client_id], back_populates="dispatch_orders_as_client")
    driver = relationship("User", foreign_keys=[driver_id], back_populates="dispatch_orders_as_driver")
    warehouse = relationship("Warehouse")
    stops = relationship("DeliveryStop", back_populates="dispatch_order", cascade="all, delete-orphan")
    items = relationship("OrderItem", back_populates="dispatch_order", cascade="all, delete-orphan")
    location_history = relationship("DispatchLocationHistory", back_populates="dispatch_order", cascade="all, delete-orphan")
    boxes = relationship("Box", back_populates="dispatch_order")

class DeliveryStop(Base):
    __tablename__ = "delivery_stops"

    id = Column(Integer, primary_key=True, index=True)
    dispatch_order_id = Column(Integer, ForeignKey("dispatch_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    stop_number = Column(Integer, nullable=False)
    address = Column(Text, nullable=False)
    latitude = Column(Numeric(10, 8), nullable=True)
    longitude = Column(Numeric(11, 8), nullable=True)
    recipient_name = Column(String(255), nullable=False)
    recipient_phone = Column(String(50), nullable=False)
    recipient_email = Column(String(255), nullable=True)
    distance_from_previous = Column(Numeric(10, 2), default=0.0)
    distance_price = Column(Numeric(10, 2), default=0.0)
    notes = Column(Text, nullable=True)
    status = Column(String(50), default="pending", index=True)
    delivered_at = Column(DateTime, nullable=True)
    proof_image = Column(String(255), nullable=True)
    signature = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    dispatch_order = relationship("DispatchOrder", back_populates="stops")

class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    dispatch_order_id = Column(Integer, ForeignKey("dispatch_orders.id", ondelete="CASCADE"), nullable=False)
    item_name = Column(String(255), nullable=False)
    quantity = Column(Integer, default=1)
    unit_price = Column(Numeric(10, 2), default=0.0)
    total_price = Column(Numeric(10, 2), default=0.0)
    description = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    dispatch_order = relationship("DispatchOrder", back_populates="items")

class DispatchLocationHistory(Base):
    __tablename__ = "dispatch_location_history"

    id = Column(Integer, primary_key=True, index=True)
    dispatch_id = Column(Integer, ForeignKey("dispatch_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    latitude = Column(Numeric(10, 8), nullable=False)
    longitude = Column(Numeric(11, 8), nullable=False)
    accuracy = Column(Numeric(10, 2), nullable=True)
    recorded_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    dispatch_order = relationship("DispatchOrder", back_populates="location_history")

class PickupRequest(Base):
    __tablename__ = "pickup_requests"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    driver_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=True)
    tracking_id = Column(String(100), unique=True, index=True, nullable=True)
    invoice_no = Column(String(100), unique=True, nullable=True)
    customer_name = Column(String(255), nullable=True)
    customer_phone = Column(String(50), nullable=True)
    pickup_address = Column(Text, nullable=True)
    destination_address = Column(Text, nullable=True)
    total_distance = Column(Numeric(10, 2), default=0.0)
    total_price = Column(Numeric(10, 2), default=0.0)
    tax_amount = Column(Numeric(10, 2), default=0.0)
    grand_total = Column(Numeric(10, 2), default=0.0)
    bill_type = Column(String(50), default="regular")
    pan_number = Column(String(50), nullable=True)
    payment_status = Column(String(50), default="pending")
    status = Column(String(50), default="pending", index=True)
    assigned_at = Column(DateTime, nullable=True)
    picked_up_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    admin_margin = Column(Numeric(10, 2), default=0.0)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    stops = relationship("PickupStop", back_populates="pickup_request", cascade="all, delete-orphan")

class PickupStop(Base):
    __tablename__ = "pickup_stops"

    id = Column(Integer, primary_key=True, index=True)
    pickup_request_id = Column(Integer, ForeignKey("pickup_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    stop_number = Column(Integer, nullable=False)
    address = Column(Text, nullable=False)
    latitude = Column(Numeric(10, 8), nullable=True)
    longitude = Column(Numeric(11, 8), nullable=True)
    contact_name = Column(String(255), nullable=False)
    contact_phone = Column(String(50), nullable=False)
    items_description = Column(Text, nullable=True)
    estimated_weight = Column(Numeric(10, 2), default=0.0)
    distance_price = Column(Numeric(10, 2), default=0.0)
    status = Column(String(50), default="pending", index=True)
    picked_up_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    pickup_request = relationship("PickupRequest", back_populates="stops")
