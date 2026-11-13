"""
Unit tests for programmatic OCR and Vision LLM discrepancy detection.
Verifies cross-validation of monetary fields without additional AI calls.
"""

from decimal import Decimal
from unittest.mock import patch, MagicMock
import pytest

from backend.schemas.receipt_schema import ReceiptExtraction, LineItem
from backend.services.discrepancy_service import (
    extract_confident_ocr_amounts,
    detect_discrepancies,
    clean_decimal,
)
from backend.services.validation_service import validate_extraction, determine_status


@pytest.fixture
def base_extraction():
    return ReceiptExtraction(
        merchant_name="The Corner Bistro",
        date="2026-02-20",
        subtotal="77.50",
        tax="6.98",
        tip="15.00",
        total_amount="99.48",
        line_items=[
            LineItem(item_name="Grilled Salmon", price="48.00"),
            LineItem(item_name="Caesar Salad", price="22.00"),
        ],
    )


class TestDiscrepancyDetection:
    """Tests for discrepancy detection between OCR and LLM extractions."""

    def test_matching_ocr_and_llm_total(self, base_extraction):
        """When OCR and LLM total match, no discrepancy warning is generated."""
        ocr_text = "THE CORNER BISTRO\nSUBTOTAL $77.50\nTAX $6.98\nTIP $15.00\nTOTAL DUE $99.48"
        warnings = detect_discrepancies(ocr_text, base_extraction)
        assert len(warnings) == 0

        # Validate through validation service
        validated = validate_extraction(base_extraction, ocr_text=ocr_text)
        assert determine_status(validated) == "COMPLETED"

    def test_different_ocr_and_llm_total(self, base_extraction):
        """When OCR total differs significantly from LLM total, discrepancy is flagged and status is REVIEW_REQUIRED."""
        ocr_text = "THE CORNER BISTRO\nSUBTOTAL $77.50\nTAX $6.98\nTOTAL DUE $43.39"
        # LLM extracted 99.48, but OCR shows 43.39
        warnings = detect_discrepancies(ocr_text, base_extraction)
        assert len(warnings) >= 1
        assert any("total amount" in w.lower() for w in warnings)
        assert any("discrepancy" in w.lower() for w in warnings)

        validated = validate_extraction(base_extraction, ocr_text=ocr_text)
        assert any("discrepancy" in w.lower() for w in validated.warnings)
        assert determine_status(validated) == "REVIEW_REQUIRED"

    def test_different_subtotal(self, base_extraction):
        """When OCR subtotal differs from LLM subtotal, discrepancy is flagged."""
        ocr_text = "THE CORNER BISTRO\nSUBTOTAL $50.00\nTOTAL DUE $99.48"
        warnings = detect_discrepancies(ocr_text, base_extraction)
        assert any("subtotal" in w.lower() for w in warnings)

        validated = validate_extraction(base_extraction, ocr_text=ocr_text)
        assert determine_status(validated) == "REVIEW_REQUIRED"

    def test_different_tax(self, base_extraction):
        """When OCR tax differs from LLM tax, discrepancy is flagged."""
        ocr_text = "THE CORNER BISTRO\nSUBTOTAL $77.50\nTAX $12.50\nTOTAL DUE $99.48"
        warnings = detect_discrepancies(ocr_text, base_extraction)
        assert any("tax" in w.lower() for w in warnings)

        validated = validate_extraction(base_extraction, ocr_text=ocr_text)
        assert determine_status(validated) == "REVIEW_REQUIRED"

    def test_different_tip(self, base_extraction):
        """When OCR tip differs from LLM tip, discrepancy is flagged."""
        ocr_text = "THE CORNER BISTRO\nTIP $5.00\nTOTAL DUE $99.48"
        warnings = detect_discrepancies(ocr_text, base_extraction)
        assert any("tip" in w.lower() for w in warnings)

        validated = validate_extraction(base_extraction, ocr_text=ocr_text)
        assert determine_status(validated) == "REVIEW_REQUIRED"

    def test_different_line_item_price(self, base_extraction):
        """When an OCR line item price differs from LLM item price, discrepancy is flagged."""
        ocr_text = "THE CORNER BISTRO\nGrilled Salmon $35.00\nTOTAL DUE $99.48"
        # Base extraction has Grilled Salmon at 48.00
        warnings = detect_discrepancies(ocr_text, base_extraction)
        assert any("grilled salmon" in w.lower() for w in warnings)

        validated = validate_extraction(base_extraction, ocr_text=ocr_text)
        assert determine_status(validated) == "REVIEW_REQUIRED"

    def test_ocr_field_unavailable(self, base_extraction):
        """When OCR does not contain labeled monetary fields, no false discrepancy is created."""
        ocr_text = "THE CORNER BISTRO\nThank you for dining with us\nOrder #849"
        warnings = detect_discrepancies(ocr_text, base_extraction)
        assert len(warnings) == 0

        validated = validate_extraction(base_extraction, ocr_text=ocr_text)
        assert determine_status(validated) == "COMPLETED"

    def test_ambiguous_ocr_amount(self, base_extraction):
        """Unlabeled numbers or noisy text in OCR do not manufacture discrepancies."""
        ocr_text = "BISTRO 12345 random 12.34 note 99.99"
        warnings = detect_discrepancies(ocr_text, base_extraction)
        assert len(warnings) == 0

    def test_currency_formatting_differences(self):
        """Differences in currency symbols or thousand commas do not create false discrepancies."""
        extraction = ReceiptExtraction(
            merchant_name="Mega Mart",
            date="2026-02-20",
            total_amount="1234.56",
            line_items=[LineItem(item_name="TV Set", price="1234.56")],
        )
        ocr_text = "Mega Mart\nTOTAL: $1,234.56"
        warnings = detect_discrepancies(ocr_text, extraction)
        assert len(warnings) == 0

    def test_no_extra_ai_call_made(self, base_extraction):
        """Discrepancy detection executes locally using regex and Decimal; zero AI API calls made."""
        ocr_text = "THE CORNER BISTRO\nTOTAL DUE $43.39"
        with patch("backend.services.llm_service.httpx.Client") as mock_client:
            warnings = detect_discrepancies(ocr_text, base_extraction)
            mock_client.assert_not_called()
        assert len(warnings) >= 1

