from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, Numeric, ForeignKey, Date
from sqlalchemy.orm import relationship
from app.core.database import Base

class Stock(Base):
    __tablename__ = "stocks"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    client_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    warehouse_request_id = Column(Integer, ForeignKey("warehouse_requests.id"), nullable=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=True)
    
    product_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    unit = Column(String(50), default="pieces")
    number_of_boxes = Column(Integer, default=0)
    quantity_per_box = Column(Integer, default=0)
    total_quantity = Column(Integer, default=0)
    remaining_quantity = Column(Integer, nullable=True)
    
    batch_id = Column(String(100), unique=True, index=True, nullable=False)
    sku = Column(String(100), unique=True, index=True, nullable=False)
    invoice_number = Column(String(100), nullable=True)
    invoice_file_path = Column(String(255), nullable=True)
    warehouse_name = Column(String(255), nullable=True)
    
    client_code = Column(String(50), nullable=False)
    client_name = Column(String(255), nullable=False)
    
    manufacturing_date = Column(Date, nullable=True)
    expiry_date = Column(Date, nullable=True)
    received_date = Column(Date, nullable=False)
    
    qr_code = Column(String(255), nullable=True)
    qr_code_data = Column(Text, nullable=True)
    
    purchase_price = Column(Numeric(10, 2), nullable=True)
    selling_price = Column(Numeric(10, 2), nullable=True)
    
    status = Column(String(50), default="in_stock", index=True)  # in_stock, partial, dispatched, expired
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    warehouse = relationship("Warehouse", back_populates="stocks")
    boxes = relationship("Box", back_populates="stock")

class Box(Base):
    __tablename__ = "boxes"

    id = Column(Integer, primary_key=True, index=True)
    batch_number = Column(String(100), index=True, nullable=True)
    box_number = Column(String(100), nullable=False)
    qr_code = Column(String(255), unique=True, index=True, nullable=False)
    qr_code_data = Column(Text, nullable=True)
    barcode = Column(String(100), index=True, nullable=True)
    entry_date = Column(Date, nullable=True)
    invoice_number = Column(String(100), nullable=True)
    shipper_name = Column(String(255), nullable=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=True, index=True)
    stock_id = Column(Integer, ForeignKey("stocks.id"), nullable=True)
    dispatch_order_id = Column(Integer, ForeignKey("dispatch_orders.id"), nullable=True)
    client_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    notes = Column(Text, nullable=True)
    received_by = Column(String(255), nullable=True)
    received_at = Column(DateTime, nullable=True)
    description = Column(Text, nullable=True)
    status = Column(String(50), default="pending", index=True)  # pending, stored, in_transit, delivered
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    warehouse = relationship("Warehouse", back_populates="boxes")
    stock = relationship("Stock", back_populates="boxes")
    dispatch_order = relationship("DispatchOrder", back_populates="boxes")
