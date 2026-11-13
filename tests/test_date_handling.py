"""
Unit tests for date extraction and date validation rules.
Verifies exact date extraction without future/past judgment, and enforces
REVIEW_REQUIRED for missing or invalid dates.
"""

from backend.schemas.receipt_schema import ReceiptExtraction, LineItem
from backend.services.validation_service import validate_extraction, determine_status
from backend.services.llm_service import EXTRACTION_PROMPT


class TestDateExtractionPromptRules:
    """Tests ensuring prompt rules instruct LLM not to judge past/future."""

    def test_prompt_forbids_future_past_judgment(self):
        """Prompt must instruct the model not to evaluate past/future or generate future warnings."""
        prompt_lower = EXTRACTION_PROMPT.lower()
        assert "not compare the receipt date" in prompt_lower
        assert "past or future" in prompt_lower
        assert "never generate warnings" in prompt_lower
        assert "never invent or estimate" in prompt_lower


class TestDateNormalizationAndParsing:
    """Tests for Pydantic date normalization."""

    def test_past_date_extracted_normally(self):
        """Past dates (e.g. 2025-05-10) are extracted normally without warnings."""
        extraction = ReceiptExtraction(
            merchant_name="Store",
            date="2025-05-10",
            total_amount="10.00",
            line_items=[LineItem(item_name="Item", price="10.00")],
        )
        assert extraction.date == "2025-05-10"
        validated = validate_extraction(extraction)
        assert determine_status(validated) == "COMPLETED"
        assert len(validated.warnings) == 0

    def test_future_looking_date_extracted_without_warning(self):
        """Dates like 2026-02-25 or 2026-11-14 are accepted without future-date warnings."""
        for test_date in ("2026-02-25", "2026-11-14"):
            extraction = ReceiptExtraction(
                merchant_name="Store",
                date=test_date,
                total_amount="10.00",
                line_items=[LineItem(item_name="Item", price="10.00")],
            )
            assert extraction.date == test_date
            validated = validate_extraction(extraction)
            assert determine_status(validated) == "COMPLETED"
            assert not any("future" in w.lower() for w in validated.warnings)

    def test_slashed_date_normalization(self):
        """US format MM/DD/YYYY is normalized into ISO YYYY-MM-DD."""
        extraction = ReceiptExtraction(
            merchant_name="Store",
            date="02/18/2026",
            total_amount="10.00",
            line_items=[LineItem(item_name="Item", price="10.00")],
        )
        assert extraction.date == "2026-02-18"
        validated = validate_extraction(extraction)
        assert determine_status(validated) == "COMPLETED"

    def test_textual_month_normalization(self):
        """Textual dates like Feb 20, 2026 are normalized into ISO format."""
        extraction = ReceiptExtraction(
            merchant_name="Store",
            date="Feb 20, 2026",
            total_amount="10.00",
            line_items=[LineItem(item_name="Item", price="10.00")],
        )
        assert extraction.date == "2026-02-20"
        validated = validate_extraction(extraction)
        assert determine_status(validated) == "COMPLETED"

    def test_missing_date_becomes_none(self):
        """Empty, null, or None dates become None and do not invent today's date."""
        for empty_val in (None, "", "null"):
            extraction = ReceiptExtraction(
                merchant_name="Store",
                date=empty_val,
                total_amount="10.00",
                line_items=[LineItem(item_name="Item", price="10.00")],
            )
            assert extraction.date is None

    def test_unreadable_date_becomes_none(self):
        """Unreadable or corrupted date strings become None."""
        extraction = ReceiptExtraction(
            merchant_name="Store",
            date="invalid-date",
            total_amount="10.00",
            line_items=[LineItem(item_name="Item", price="10.00")],
        )
        assert extraction.date is None

    def test_impossible_calendar_date_becomes_none(self):
        """Impossible calendar dates like 2026-02-31 become None."""
        for bad_date in ("2026-02-31", "02/31/2026", "2026-13-45"):
            extraction = ReceiptExtraction(
                merchant_name="Store",
                date=bad_date,
                total_amount="10.00",
                line_items=[LineItem(item_name="Item", price="10.00")],
            )
            assert extraction.date is None


class TestDateValidationStatusEnforcement:
    """Tests ensuring missing or invalid dates strictly enforce REVIEW_REQUIRED."""

    def test_valid_date_allows_completed(self):
        """Valid date allows COMPLETED status when all required fields are present."""
        extraction = ReceiptExtraction(
            merchant_name="Store",
            date="2026-02-20",
            total_amount="10.00",
            line_items=[LineItem(item_name="Item", price="10.00")],
        )
        validated = validate_extraction(extraction)
        assert determine_status(validated) == "COMPLETED"

    def test_missing_date_enforces_review_required(self):
        """Missing receipt date strictly requires REVIEW_REQUIRED status."""
        extraction = ReceiptExtraction(
            merchant_name="Store",
            date=None,
            total_amount="10.00",
            line_items=[LineItem(item_name="Item", price="10.00")],
        )
        validated = validate_extraction(extraction)
        assert any("date" in w.lower() for w in validated.warnings)
        assert determine_status(validated) == "REVIEW_REQUIRED"

    def test_invalid_date_enforces_review_required(self):
        """Unparseable string as date enforces REVIEW_REQUIRED status."""
        extraction = ReceiptExtraction(
            merchant_name="Store",
            date="invalid-date",
            total_amount="10.00",
            line_items=[LineItem(item_name="Item", price="10.00")],
        )
        validated = validate_extraction(extraction)
        assert any("date" in w.lower() for w in validated.warnings)
        assert determine_status(validated) == "REVIEW_REQUIRED"

    def test_impossible_calendar_date_enforces_review_required(self):
        """Invalid calendar date enforces REVIEW_REQUIRED status."""
        extraction = ReceiptExtraction(
            merchant_name="Store",
            date="2026-02-31",
            total_amount="10.00",
            line_items=[LineItem(item_name="Item", price="10.00")],
        )
        validated = validate_extraction(extraction)
        assert any("date" in w.lower() for w in validated.warnings)
        assert determine_status(validated) == "REVIEW_REQUIRED"

