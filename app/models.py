from sqlalchemy import Column, Integer, String, Float, DateTime, Text, ForeignKey, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()


class Receipt(Base):
    """
    Receipt table - stores main receipt information
    """
    __tablename__ = "receipts"
    
    id = Column(Integer, primary_key=True, index=True)
    merchant_name = Column(String(255), nullable=False)
    date = Column(String(50), nullable=False)  # YYYY-MM-DD
    time = Column(String(50), nullable=True)   # HH:MM
    subtotal = Column(Float, default=0.0)
    tax = Column(Float, default=0.0)
    total = Column(Float, nullable=False)
    payment_method = Column(String(100), nullable=True)
    category = Column(String(50), nullable=False)  # groceries, restaurant, etc.
    
    # File info
    filename = Column(String(255), nullable=False)
    file_path = Column(Text, nullable=False)
    
    # Metadata
    processed_at = Column(DateTime, default=datetime.utcnow)
    ai_model = Column(String(100), nullable=True)
    
    # Relationships
    items = relationship("ReceiptItem", back_populates="receipt", cascade="all, delete-orphan")
    
    def to_dict(self):
        """Convert to dictionary for JSON response"""
        return {
            "id": self.id,
            "merchant_name": self.merchant_name,
            "date": self.date,
            "time": self.time,
            "subtotal": self.subtotal,
            "tax": self.tax,
            "total": self.total,
            "payment_method": self.payment_method,
            "category": self.category,
            "filename": self.filename,
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
            "ai_model": self.ai_model,
            "items": [item.to_dict() for item in self.items]
        }


class ReceiptItem(Base):
    """
    Receipt items table - stores individual line items
    """
    __tablename__ = "receipt_items"
    
    id = Column(Integer, primary_key=True, index=True)
    receipt_id = Column(Integer, ForeignKey("receipts.id"), nullable=False)
    name = Column(String(255), nullable=False)
    quantity = Column(Integer, default=1)
    price = Column(Float, nullable=False)
    
    # Relationship
    receipt = relationship("Receipt", back_populates="items")
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            "id": self.id,
            "name": self.name,
            "quantity": self.quantity,
            "price": self.price
        }