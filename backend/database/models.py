"""
Database ORM models.

SQLAlchemy models for receipts and receipt line items.
Includes Phase 2 execution metadata (model_used, extraction_method, fallback tracking).
"""

from datetime import datetime, date
from decimal import Decimal

from sqlalchemy import (
    Column,
    Integer,
    String,
    Date,
    DateTime,
    Numeric,
    Text,
    Boolean,
    ForeignKey,
)
from sqlalchemy.orm import relationship

from backend.database.connection import Base


class Receipt(Base):
    """ORM model for the receipts table."""

    __tablename__ = "receipts"

    id: int = Column(Integer, primary_key=True, autoincrement=True, index=True)
    filename: str = Column(String(255), nullable=False)
    file_path: str = Column(String(500), nullable=False)
    merchant_name: str | None = Column(String(255), nullable=True)
    date: date | None = Column(Date, nullable=True)
    subtotal: Decimal | None = Column(Numeric(10, 2), nullable=True)
    tax: Decimal | None = Column(Numeric(10, 2), nullable=True)
    tip: Decimal | None = Column(Numeric(10, 2), nullable=True)
    total_amount: Decimal | None = Column(Numeric(10, 2), nullable=True)
    extracted_json: str | None = Column(Text, nullable=True)
    raw_ocr_text: str | None = Column(Text, nullable=True)
    status: str = Column(String(50), nullable=False, default="PROCESSING")
    created_at: datetime = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Phase 2 metadata
    model_used: str | None = Column(String(100), nullable=True)
    extraction_method: str | None = Column(String(50), nullable=True, default="AI")
    fallback_used: bool = Column(Boolean, nullable=False, default=False)
    fallback_reason: str | None = Column(Text, nullable=True)
    processing_duration_ms: int | None = Column(Integer, nullable=True)

    # Relationship to line items
    line_items = relationship(
        "ReceiptItem",
        back_populates="receipt",
        cascade="all, delete-orphan",
        lazy="joined",
    )

    def __repr__(self) -> str:
        return (
            f"<Receipt(id={self.id}, merchant='{self.merchant_name}', "
            f"total={self.total_amount}, method='{self.extraction_method}')>"
        )


class ReceiptItem(Base):
    """ORM model for the receipt_items table."""

    __tablename__ = "receipt_items"

    id: int = Column(Integer, primary_key=True, autoincrement=True, index=True)
    receipt_id: int = Column(Integer, ForeignKey("receipts.id"), nullable=False)
    item_name: str = Column(String(500), nullable=False)
    price: Decimal | None = Column(Numeric(10, 2), nullable=True)

    # Relationship back to receipt
    receipt = relationship("Receipt", back_populates="line_items")

    def __repr__(self) -> str:
        return f"<ReceiptItem(id={self.id}, name='{self.item_name}', price={self.price})>"
