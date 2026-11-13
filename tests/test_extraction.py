"""
Tests for extraction, OCR, and LLM services.

Mocks external dependencies to test the extraction pipeline.
"""

import json
import pytest
from unittest.mock import patch, MagicMock
from PIL import Image
import io

from backend.services.extraction_service import _parse_llm_response
from backend.schemas.receipt_schema import ReceiptExtraction


class TestLLMResponseParsing:
    """Tests for parsing LLM JSON responses."""

    def test_parse_valid_json(self):
        """Valid JSON string should parse correctly."""
        raw = json.dumps({
            "merchant_name": "Store",
            "date": "2026-01-01",
            "line_items": [],
            "subtotal": "10.00",
            "tax": "0.80",
            "tip": None,
            "total_amount": "10.80",
            "warnings": [],
        })
        result = _parse_llm_response(raw)
        assert result["merchant_name"] == "Store"
        assert result["total_amount"] == "10.80"

    def test_parse_json_with_markdown_fences(self):
        """JSON wrapped in markdown code fences should parse."""
        raw = '```json\n{"merchant_name": "Store", "total_amount": "5.00"}\n```'
        result = _parse_llm_response(raw)
        assert result["merchant_name"] == "Store"

    def test_parse_json_with_surrounding_text(self):
        """JSON embedded in surrounding text should be extracted."""
        raw = 'Here is the result:\n{"merchant_name": "Store"}\nDone.'
        result = _parse_llm_response(raw)
        assert result["merchant_name"] == "Store"

    def test_parse_invalid_json_raises(self):
        """Completely invalid JSON should raise ExtractionError."""
        from backend.utils.exceptions import ExtractionError
        with pytest.raises(ExtractionError):
            _parse_llm_response("This is not JSON at all")

    def test_parse_empty_response(self):
        """Empty response should raise ExtractionError."""
        from backend.utils.exceptions import ExtractionError
        with pytest.raises(ExtractionError):
            _parse_llm_response("")


class TestOCRService:
    """Tests for OCR service functionality."""

    @patch("backend.services.ocr_service._get_reader")
    def test_extract_text_from_image(self, mock_get_reader):
        """OCR should extract text from a valid image."""
        from backend.services.ocr_service import extract_text_from_image

        mock_reader = MagicMock()
        mock_reader.readtext.return_value = ["Hello", "World"]
        mock_get_reader.return_value = mock_reader

        img = Image.new("RGB", (100, 100), color="white")
        result = extract_text_from_image(img)

        assert "Hello" in result
        assert "World" in result
        mock_reader.readtext.assert_called_once()

    @patch("backend.services.ocr_service._get_reader")
    def test_extract_text_empty_result(self, mock_get_reader):
        """OCR with no text detected should return empty string."""
        from backend.services.ocr_service import extract_text_from_image

        mock_reader = MagicMock()
        mock_reader.readtext.return_value = []
        mock_get_reader.return_value = mock_reader

        img = Image.new("RGB", (100, 100), color="white")
        result = extract_text_from_image(img)

        assert result == ""


class TestLLMService:
    """Tests for LLM service functionality."""

    def test_llm_auth_error_without_key(self):
        """LLM service should raise auth error when no API key is set."""
        from backend.services.llm_service import extract_receipt_data
        from backend.utils.exceptions import LLMAuthenticationError

        img = Image.new("RGB", (100, 100), color="white")

        with patch("backend.services.llm_service.settings") as mock_settings:
            mock_settings.OPENROUTER_API_KEY = ""
            mock_settings.OPENROUTER_MODEL = "test-model"
            mock_settings.OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

            with pytest.raises(LLMAuthenticationError):
                extract_receipt_data(img, "test OCR text")

    @patch("backend.services.llm_service.httpx.Client")
    def test_llm_successful_call(self, mock_client_class):
        """LLM service should return content on successful API call."""
        from backend.services.llm_service import extract_receipt_data

        expected_response = json.dumps({
            "merchant_name": "Test",
            "total_amount": "10.00",
        })

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": expected_response}}]
        }

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        img = Image.new("RGB", (100, 100), color="white")

        with patch("backend.services.llm_service.settings") as mock_settings:
            mock_settings.OPENROUTER_API_KEY = "test-key-123"
            mock_settings.OPENROUTER_MODEL = "test-model"
            mock_settings.OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

            result = extract_receipt_data(img, "test OCR text")

        assert "Test" in result

    @patch("backend.services.llm_service.httpx.Client")
    def test_llm_rate_limit(self, mock_client_class):
        """LLM service should raise rate limit error on 429."""
        from backend.services.llm_service import extract_receipt_data
        from backend.utils.exceptions import LLMRateLimitError

        mock_response = MagicMock()
        mock_response.status_code = 429

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        img = Image.new("RGB", (100, 100), color="white")

        with patch("backend.services.llm_service.settings") as mock_settings:
            mock_settings.OPENROUTER_API_KEY = "test-key-123"
            mock_settings.OPENROUTER_MODEL = "test-model"
            mock_settings.OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

            with pytest.raises(LLMRateLimitError):
                extract_receipt_data(img, "test text")

