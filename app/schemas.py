from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


class ReceiptItemCreate(BaseModel):
    """Schema for creating receipt item"""
    name: str
    quantity: int = 1
    price: float


class ReceiptItemResponse(BaseModel):
    """Schema for receipt item response"""
    id: int
    name: str
    quantity: int
    price: float
    
    class Config:
        from_attributes = True


class ReceiptCreate(BaseModel):
    """Schema for creating receipt"""
    merchant_name: str
    date: str
    time: Optional[str] = None
    subtotal: float = 0.0
    tax: float = 0.0
    total: float
    payment_method: Optional[str] = None
    category: str
    filename: str
    file_path: str
    ai_model: Optional[str] = None
    items: List[ReceiptItemCreate]


class ReceiptResponse(BaseModel):
    """Schema for receipt response"""
    id: int
    merchant_name: str
    date: str
    time: Optional[str]
    subtotal: float
    tax: float
    total: float
    payment_method: Optional[str]
    category: str
    filename: str
    processed_at: Optional[datetime]
    ai_model: Optional[str]
    items: List[ReceiptItemResponse]
    
    class Config:
        from_attributes = True


class AnalyticsResponse(BaseModel):
    """Schema for analytics response"""
    total_receipts: int
    total_spent: float
    by_category: dict
    by_month: dict
    recent_receipts: List[ReceiptResponse]