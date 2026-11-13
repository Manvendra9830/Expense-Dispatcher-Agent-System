"""
Unit tests for the Local OCR-based receipt parser.
Tests regex heuristics, date parsing, line item extraction, and safety rules.
Zero external network calls.
"""

import pytest
from backend.services.local_receipt_parser import (
    parse_receipt_text_locally,
    parse_date,
    extract_merchant,
)
from backend.schemas.receipt_schema import ReceiptExtraction


class TestLocalParserDates:
    """Tests for local date parsing."""

    def test_parse_iso_date(self):
        text = "Order #123\nDate: 2026-02-20\nTotal: $10.00"
        assert parse_date(text) == "2026-02-20"

    def test_parse_textual_month(self):
        text = "THE CORNER BISTRO\nFeb 20, 2026 14:32\nTotal: $99.48"
        assert parse_date(text) == "2026-02-20"

    def test_parse_slashed_date(self):
        text = "TARGET STORES\nDate: 02/18/2026\nTotal: $50.31"
        assert parse_date(text) == "2026-02-18"

    def test_unparseable_date_returns_none(self):
        text = "No date found on this receipt"
        assert parse_date(text) is None


class TestLocalParserMerchant:
    """Tests for merchant identification."""

    def test_extract_merchant_first_line(self):
        lines = ["THE CORNER BISTRO", "Table 12", "Feb 20, 2026"]
        assert extract_merchant(lines) == "THE CORNER BISTRO"

    def test_extract_merchant_skipping_order_headers(self):
        lines = ["Order #849", "Table #12", "THE CORNER BISTRO", "Date: Feb 20, 2026"]
        assert extract_merchant(lines) == "THE CORNER BISTRO"


class TestLocalReceiptParser:
    """Full heuristic extraction tests."""

    def test_parse_corner_bistro_sample(self):
        ocr_text = """THE CORNER BISTRO
Order #849 Table 12
Date: Feb 20, 2026 14:30
Sparkling Water 4.00
Caesar Salad 22.00
Grilled Salmon 48.00
Espresso 3.50
Subtotal: $77.50
Tax: $6.98
Tip: $15.00
Total: $99.48
Thank you for dining with us!"""

        result = parse_receipt_text_locally(ocr_text)

        assert isinstance(result, ReceiptExtraction)
        assert result.merchant_name == "THE CORNER BISTRO"
        assert result.date == "2026-02-20"
        assert result.subtotal == "77.50"
        assert result.tax == "6.98"
        assert result.tip == "15.00"
        assert result.total_amount == "99.48"
        assert len(result.line_items) == 4
        assert result.line_items[0].item_name == "Sparkling Water"
        assert result.line_items[0].price == "4.00"

    def test_parse_target_sample(self):
        ocr_text = """TARGET STORES
1234 Main Street
Date: 02/18/2026
Wireless Mouse 24.99
USB-C Cable 6ft 12.50
Notebook 3-Pack 8.99
Subtotal: 46.48
Tax: 3.83
Total Amount: 50.31"""

        result = parse_receipt_text_locally(ocr_text)

        assert result.merchant_name == "TARGET STORES"
        assert result.date == "2026-02-18"
        assert result.subtotal == "46.48"
        assert result.tax == "3.83"
        assert result.tip is None
        assert result.total_amount == "50.31"
        assert len(result.line_items) == 3

    def test_empty_ocr_text_safe_handling(self):
        result = parse_receipt_text_locally("")
        assert result.merchant_name is None
        assert result.total_amount is None
        assert len(result.warnings) > 0

    def test_no_fabricated_values(self):
        ocr_text = "Some random text without any prices or merchant name"
        result = parse_receipt_text_locally(ocr_text)
        assert result.subtotal is None
        assert result.tax is None
        assert result.tip is None
        assert result.total_amount is None
        assert len(result.line_items) == 0
