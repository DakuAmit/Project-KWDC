from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Numeric, ForeignKey, Date
from sqlalchemy.orm import relationship
from app.core.database import Base

class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    client_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    warehouse_request_id = Column(Integer, ForeignKey("warehouse_requests.id"), nullable=True)
    invoice_number = Column(String(100), unique=True, index=True, nullable=False)
    order_type = Column(String(50), nullable=True)  # dispatch, warehouse, equipment, security
    order_id = Column(Integer, nullable=True)
    
    amount = Column(Numeric(10, 2), default=0.0)
    subtotal = Column(Numeric(12, 2), default=0.0)
    discount = Column(Numeric(12, 2), default=0.0)
    tax_rate = Column(Numeric(5, 2), default=13.00)  # Nepal 13% VAT
    tax_amount = Column(Numeric(12, 2), default=0.0)
    grand_total = Column(Numeric(12, 2), default=0.0)
    
    billing_type = Column(String(50), default="regular")
    pan_number = Column(String(50), nullable=True)
    billing_address = Column(Text, nullable=True)
    items = Column(Text, nullable=True)  # JSON encoded list of line items
    
    status = Column(String(50), default="pending", index=True)
    payment_status = Column(String(50), default="unpaid", index=True)  # unpaid, paid, partial
    due_date = Column(Date, nullable=True)
    payment_due_date = Column(Date, nullable=True)
    paid_at = Column(DateTime, nullable=True)
    payment_method = Column(String(50), nullable=True)
    qr_code = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", foreign_keys=[user_id], back_populates="invoices")
    warehouse_request = relationship("WarehouseRequest", back_populates="invoices")
    transactions = relationship("Transaction", back_populates="invoice", cascade="all, delete-orphan")

    @property
    def total_amount(self):
        return float(self.grand_total or self.amount or 0.0)

    @property
    def vat_amount(self):
        return float(self.tax_amount or 0.0)

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    tax = Column(Numeric(10, 2), default=0.0)
    payment_method = Column(String(50), nullable=False)  # esewa, khalti, stripe, bank_transfer, nepalpay
    transaction_id = Column(String(100), unique=True, index=True, nullable=False)
    receipt_no = Column(String(100), unique=True, nullable=True)
    status = Column(String(50), default="pending", index=True)  # pending, completed, failed
    payment_date = Column(DateTime, default=datetime.utcnow)
    payment_details = Column(Text, nullable=True)  # JSON encoded gateway callback response
    notes = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    invoice = relationship("Invoice", back_populates="transactions")
    user = relationship("User")

class MarginTier(Base):
    __tablename__ = "margin_tiers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    min_distance = Column(Numeric(10, 2), default=0.0)
    max_distance = Column(Numeric(10, 2), nullable=True)
    service_type = Column(String(50), default="dispatch")  # dispatch, pickup, warehouse, equipment
    margin_type = Column(String(50), default="percentage")  # percentage, flat
    margin_value = Column(Numeric(10, 2), default=0.0)
    is_active = Column(Boolean, default=True, index=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class PartnerEarning(Base):
    __tablename__ = "partner_earnings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    role = Column(String(50), nullable=False)
    amount = Column(Numeric(12, 2), default=0.0)
    order_type = Column(String(50), nullable=False)
    order_id = Column(Integer, nullable=False)
    status = Column(String(50), default="pending")  # pending, paid
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
