"""
Pydantic schemas for receipt data validation.

Defines the structure for extraction results, API responses, and validation.
Includes Phase 2 metadata fields for model and fallback observability.
"""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class LineItem(BaseModel):
    """Schema for a single receipt line item."""

    item_name: str = Field(..., min_length=1, description="Name of the item")
    price: Optional[str] = Field(None, description="Price as a string (decimal)")

    @field_validator("price", mode="before")
    @classmethod
    def validate_price(cls, v):
        if v is None:
            return v
        # Convert numeric types to string
        if isinstance(v, (int, float)):
            v = str(v)
        if isinstance(v, str):
            # Remove currency symbols and whitespace
            cleaned = v.replace("$", "").replace("€", "").replace("£", "").strip()
            if cleaned == "" or cleaned.lower() == "null":
                return None
            try:
                Decimal(cleaned)
                return cleaned
            except InvalidOperation:
                return None
        return v


class ReceiptExtraction(BaseModel):
    """Schema for the complete extraction result from a receipt."""

    merchant_name: Optional[str] = Field(None, description="Merchant or store name")
    date: Optional[str] = Field(None, description="Receipt date in YYYY-MM-DD format")
    line_items: list[LineItem] = Field(default_factory=list, description="List of line items")
    subtotal: Optional[str] = Field(None, description="Subtotal amount")
    tax: Optional[str] = Field(None, description="Tax amount")
    tip: Optional[str] = Field(None, description="Tip/gratuity amount")
    total_amount: Optional[str] = Field(None, description="Total amount")
    warnings: list[str] = Field(default_factory=list, description="Validation warnings")

    @field_validator("date", mode="before")
    @classmethod
    def validate_date(cls, v):
        if v is None or v == "" or v == "null":
            return None
        if isinstance(v, str):
            try:
                date.fromisoformat(v)
                return v
            except ValueError:
                # Try common date formats
                import re
                v = v.strip()
                match = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", v)
                if match:
                    m, d, y = match.groups()
                    try:
                        parsed = date(int(y), int(m), int(d))
                        return parsed.isoformat()
                    except ValueError:
                        pass
                return None
        return None

    @field_validator("subtotal", "tax", "tip", "total_amount", mode="before")
    @classmethod
    def validate_monetary(cls, v):
        if v is None:
            return v
        if isinstance(v, (int, float)):
            v = str(v)
        if isinstance(v, str):
            cleaned = v.replace("$", "").replace("€", "").replace("£", "").replace(",", "").strip()
            if cleaned == "" or cleaned.lower() == "null" or cleaned.lower() == "none":
                return None
            try:
                Decimal(cleaned)
                return cleaned
            except InvalidOperation:
                return None
        return v


class ReceiptResponse(BaseModel):
    """API response schema for a single receipt."""

    id: int
    filename: str
    merchant_name: Optional[str] = None
    date: Optional[str] = None
    line_items: list[LineItem] = Field(default_factory=list)
    subtotal: Optional[float] = None
    tax: Optional[float] = None
    tip: Optional[float] = None
    total_amount: Optional[float] = None
    status: str
    warnings: list[str] = Field(default_factory=list)
    raw_ocr_text: Optional[str] = None
    created_at: Optional[str] = None

    # Phase 2 metadata
    model_used: Optional[str] = None
    extraction_method: Optional[str] = "AI"
    fallback_used: Optional[bool] = False
    fallback_reason: Optional[str] = None
    processing_duration_ms: Optional[int] = None

    class Config:
        from_attributes = True


class ReceiptListItem(BaseModel):
    """Simplified receipt schema for list views."""

    id: int
    filename: str
    merchant_name: Optional[str] = None
    date: Optional[str] = None
    total_amount: Optional[float] = None
    status: str
    created_at: Optional[str] = None

    # Phase 2 metadata
    model_used: Optional[str] = None
    extraction_method: Optional[str] = "AI"
    fallback_used: Optional[bool] = False

    class Config:
        from_attributes = True


class DashboardStats(BaseModel):
    """Dashboard statistics schema."""

    total_receipts: int = 0
    total_expenses: float = 0.0
    successful_extractions: int = 0
    review_required: int = 0


class ErrorResponse(BaseModel):
    """Standard error response schema."""

    detail: str
    status_code: int = 500
