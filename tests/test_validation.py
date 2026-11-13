"""
Tests for Pydantic validation and business validation.
"""

import pytest
from decimal import Decimal

from backend.schemas.receipt_schema import ReceiptExtraction, LineItem
from backend.services.validation_service import validate_extraction, determine_status


class TestPydanticValidation:
    """Tests for Pydantic schema validation."""

    def test_valid_extraction(self):
        """A complete, valid extraction should pass validation."""
        extraction = ReceiptExtraction(
            merchant_name="Target Stores",
            date="2026-02-18",
            line_items=[
                LineItem(item_name="Wireless Mouse", price="24.99"),
                LineItem(item_name="USB Cable", price="9.99"),
            ],
            subtotal="34.98",
            tax="2.80",
            tip=None,
            total_amount="37.78",
            warnings=[],
        )
        assert extraction.merchant_name == "Target Stores"
        assert extraction.date == "2026-02-18"
        assert len(extraction.line_items) == 2
        assert extraction.total_amount == "37.78"

    def test_nullable_fields(self):
        """Optional fields should accept None."""
        extraction = ReceiptExtraction(
            merchant_name=None,
            date=None,
            line_items=[],
            subtotal=None,
            tax=None,
            tip=None,
            total_amount=None,
        )
        assert extraction.merchant_name is None
        assert extraction.total_amount is None

    def test_date_validation_iso(self):
        """ISO format dates should be accepted."""
        extraction = ReceiptExtraction(date="2026-12-25")
        assert extraction.date == "2026-12-25"

    def test_date_validation_us_format(self):
        """US format dates (MM/DD/YYYY) should be converted to ISO."""
        extraction = ReceiptExtraction(date="12/25/2026")
        assert extraction.date == "2026-12-25"

    def test_invalid_date_returns_none(self):
        """Unparseable dates should become None."""
        extraction = ReceiptExtraction(date="not-a-date")
        assert extraction.date is None

    def test_monetary_with_dollar_sign(self):
        """Monetary values with $ should be cleaned."""
        extraction = ReceiptExtraction(total_amount="$42.50")
        assert extraction.total_amount == "42.50"

    def test_monetary_with_comma(self):
        """Monetary values with commas should be cleaned."""
        extraction = ReceiptExtraction(total_amount="1,234.56")
        assert extraction.total_amount == "1234.56"

    def test_invalid_monetary_returns_none(self):
        """Non-numeric monetary values should become None."""
        extraction = ReceiptExtraction(total_amount="not-a-number")
        assert extraction.total_amount is None

    def test_line_item_price_cleaning(self):
        """Line item prices should be cleaned of currency symbols."""
        item = LineItem(item_name="Widget", price="$19.99")
        assert item.price == "19.99"

    def test_line_item_null_price(self):
        """Line items should accept null prices."""
        item = LineItem(item_name="Unknown Item", price=None)
        assert item.price is None

    def test_line_item_numeric_price(self):
        """Line items should handle numeric price values."""
        item = LineItem(item_name="Widget", price="15.50")
        assert item.price == "15.50"


class TestBusinessValidation:
    """Tests for business validation rules."""

    def test_missing_merchant_warning(self):
        """Missing merchant name should generate a warning."""
        extraction = ReceiptExtraction(
            merchant_name=None,
            total_amount="10.00",
        )
        result = validate_extraction(extraction)
        assert any("Merchant name" in w for w in result.warnings)

    def test_missing_date_warning(self):
        """Missing date should generate a warning."""
        extraction = ReceiptExtraction(
            merchant_name="Store",
            date=None,
            total_amount="10.00",
        )
        result = validate_extraction(extraction)
        assert any("date" in w.lower() for w in result.warnings)

    def test_missing_total_warning(self):
        """Missing total amount should generate a warning."""
        extraction = ReceiptExtraction(
            merchant_name="Store",
            total_amount=None,
        )
        result = validate_extraction(extraction)
        assert any("Total amount" in w for w in result.warnings)

    def test_negative_amount_warning(self):
        """Negative amounts should be flagged."""
        extraction = ReceiptExtraction(
            merchant_name="Store",
            total_amount="-10.00",
        )
        result = validate_extraction(extraction)
        assert any("negative" in w.lower() for w in result.warnings)

    def test_arithmetic_consistency_pass(self):
        """Consistent arithmetic should not generate extra warnings."""
        extraction = ReceiptExtraction(
            merchant_name="Store",
            date="2026-01-01",
            subtotal="10.00",
            tax="0.80",
            tip="2.00",
            total_amount="12.80",
            line_items=[LineItem(item_name="Item", price="10.00")],
        )
        result = validate_extraction(extraction)
        arithmetic_warnings = [w for w in result.warnings if "Arithmetic" in w]
        assert len(arithmetic_warnings) == 0

    def test_arithmetic_inconsistency_warning(self):
        """Inconsistent totals should generate a warning."""
        extraction = ReceiptExtraction(
            merchant_name="Store",
            subtotal="10.00",
            tax="0.80",
            total_amount="20.00",  # Way off
        )
        result = validate_extraction(extraction)
        assert any("Arithmetic" in w for w in result.warnings)

    def test_empty_line_items_warning(self):
        """Empty line items should generate a warning."""
        extraction = ReceiptExtraction(
            merchant_name="Store",
            total_amount="10.00",
        )
        result = validate_extraction(extraction)
        assert any("No line items" in w for w in result.warnings)


class TestStatusDetermination:
    """Tests for processing status determination."""

    def test_completed_status(self):
        """Good extraction should result in COMPLETED status."""
        extraction = ReceiptExtraction(
            merchant_name="Store",
            date="2026-01-01",
            total_amount="10.00",
            line_items=[LineItem(item_name="Item", price="10.00")],
        )
        extraction = validate_extraction(extraction)
        status = determine_status(extraction)
        assert status == "COMPLETED"

    def test_review_required_missing_fields(self):
        """Too many missing critical fields should result in REVIEW_REQUIRED."""
        extraction = ReceiptExtraction(
            merchant_name=None,
            total_amount=None,
            line_items=[],
        )
        extraction = validate_extraction(extraction)
        status = determine_status(extraction)
        assert status == "REVIEW_REQUIRED"

    def test_review_required_negative(self):
        """Negative values should result in REVIEW_REQUIRED."""
        extraction = ReceiptExtraction(
            merchant_name="Store",
            total_amount="-5.00",
            line_items=[LineItem(item_name="Item", price="5.00")],
        )
        extraction = validate_extraction(extraction)
        status = determine_status(extraction)
        assert status == "REVIEW_REQUIRED"

