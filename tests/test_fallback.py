"""
Unit tests for the Model Fallback Service.
Verifies sequential fallback: Primary -> Fallback A -> Fallback B -> Local OCR.
All external LLM requests are mocked.
"""

import json
from unittest.mock import patch, MagicMock
from PIL import Image
import pytest

from backend.services.model_fallback_service import extract_with_fallback
from backend.utils.exceptions import (
    LLMAuthenticationError,
    LLMRateLimitError,
    LLMModelUnavailableError,
    LLMError,
)


@pytest.fixture
def dummy_image():
    return Image.new("RGB", (50, 50), color="white")


@pytest.fixture
def sample_ai_response():
    return json.dumps({
        "merchant_name": "AI Bistro",
        "date": "2026-02-20",
        "line_items": [{"item_name": "Salad", "price": "10.00"}],
        "subtotal": "10.00",
        "tax": "1.00",
        "tip": None,
        "total_amount": "11.00",
        "warnings": [],
    })


class TestModelFallbackService:
    """Tests for sequential model fallback execution."""

    @patch("backend.services.model_fallback_service.extract_receipt_data")
    @patch("backend.services.model_fallback_service.is_account_quota_exhausted", return_value=False)
    def test_primary_model_success(self, mock_quota, mock_llm, dummy_image, sample_ai_response):
        """When primary model succeeds, no fallback should be used."""
        mock_llm.return_value = sample_ai_response

        with patch("backend.services.model_fallback_service.settings") as mock_settings:
            mock_settings.OPENROUTER_API_KEY = "sk-test"
            mock_settings.OPENROUTER_PRIMARY_MODEL = "nvidia/nemotron-3.5-super-vl:free"
            mock_settings.OPENROUTER_FALLBACK_MODELS = ["google/gemma-4-31b-it:free"]
            mock_settings.ALLOW_PAID_MODELS = False
            mock_settings.get_all_configured_models.return_value = [
                "nvidia/nemotron-3.5-super-vl:free",
                "google/gemma-4-31b-it:free",
            ]
            mock_settings.is_free_model.side_effect = lambda m: m.endswith(":free")

            result = extract_with_fallback(dummy_image, "Sample OCR text")

            assert result.extraction_method == "AI"
            assert result.model_used == "nvidia/nemotron-3.5-super-vl:free"
            assert result.fallback_used is False
            assert result.extraction.merchant_name == "AI Bistro"
            assert mock_llm.call_count == 1

    @patch("backend.services.model_fallback_service.extract_receipt_data")
    @patch("backend.services.model_fallback_service.is_account_quota_exhausted", return_value=False)
    def test_fallback_to_model_a(self, mock_quota, mock_llm, dummy_image, sample_ai_response):
        """When primary model fails with 404, fallback model A is used."""
        # Primary fails with 404, Fallback succeeds
        mock_llm.side_effect = [
            LLMModelUnavailableError("Model not found"),
            sample_ai_response,
        ]

        with patch("backend.services.model_fallback_service.settings") as mock_settings:
            mock_settings.OPENROUTER_API_KEY = "sk-test"
            mock_settings.OPENROUTER_PRIMARY_MODEL = "nvidia/nemotron-3.5-super-vl:free"
            mock_settings.OPENROUTER_FALLBACK_MODELS = ["google/gemma-4-31b-it:free"]
            mock_settings.ALLOW_PAID_MODELS = False
            mock_settings.get_all_configured_models.return_value = [
                "nvidia/nemotron-3.5-super-vl:free",
                "google/gemma-4-31b-it:free",
            ]
            mock_settings.is_free_model.side_effect = lambda m: m.endswith(":free")

            result = extract_with_fallback(dummy_image, "Sample OCR text")

            assert result.extraction_method == "AI"
            assert result.model_used == "google/gemma-4-31b-it:free"
            assert result.fallback_used is True
            assert "Model not found" in (result.fallback_reason or "")
            assert mock_llm.call_count == 2

    @patch("backend.services.model_fallback_service.extract_receipt_data")
    @patch("backend.services.model_fallback_service.is_account_quota_exhausted", return_value=False)
    def test_fallback_to_local_ocr_when_all_ai_fail(self, mock_quota, mock_llm, dummy_image):
        """When all AI models fail with rate limits or server errors, local OCR parser is used."""
        mock_llm.side_effect = [
            LLMRateLimitError("429 Rate limit"),
            LLMError("500 Server error"),
        ]

        sample_ocr = "THE CORNER BISTRO\nDate: 2026-02-20\nCoffee 3.50\nTotal: 3.50"

        with patch("backend.services.model_fallback_service.settings") as mock_settings:
            mock_settings.OPENROUTER_API_KEY = "sk-test"
            mock_settings.OPENROUTER_PRIMARY_MODEL = "nvidia/nemotron-3.5-super-vl:free"
            mock_settings.OPENROUTER_FALLBACK_MODELS = ["google/gemma-4-31b-it:free"]
            mock_settings.ALLOW_PAID_MODELS = False
            mock_settings.get_all_configured_models.return_value = [
                "nvidia/nemotron-3.5-super-vl:free",
                "google/gemma-4-31b-it:free",
            ]
            mock_settings.is_free_model.side_effect = lambda m: m.endswith(":free")

            result = extract_with_fallback(dummy_image, sample_ocr)

            assert result.extraction_method == "LOCAL_OCR"
            assert result.model_used is None
            assert result.fallback_used is True
            assert result.extraction.merchant_name == "THE CORNER BISTRO"
            assert result.extraction.total_amount == "3.50"

    @patch("backend.services.model_fallback_service.extract_receipt_data")
    @patch("backend.services.model_fallback_service.is_account_quota_exhausted", return_value=False)
    def test_auth_error_halts_ai_immediately(self, mock_quota, mock_llm, dummy_image):
        """A 401 Auth error stops all subsequent AI attempts and falls back to local OCR immediately."""
        mock_llm.side_effect = LLMAuthenticationError("Invalid API key")

        sample_ocr = "TARGET STORES\nTotal: 25.00"

        with patch("backend.services.model_fallback_service.settings") as mock_settings:
            mock_settings.OPENROUTER_API_KEY = "sk-invalid"
            mock_settings.OPENROUTER_PRIMARY_MODEL = "nvidia/nemotron-3.5-super-vl:free"
            mock_settings.OPENROUTER_FALLBACK_MODELS = ["google/gemma-4-31b-it:free", "particle-ai/particle-1:free"]
            mock_settings.ALLOW_PAID_MODELS = False
            mock_settings.get_all_configured_models.return_value = [
                "nvidia/nemotron-3.5-super-vl:free",
                "google/gemma-4-31b-it:free",
                "particle-ai/particle-1:free",
            ]
            mock_settings.is_free_model.side_effect = lambda m: m.endswith(":free")

            result = extract_with_fallback(dummy_image, sample_ocr)

            # Must have attempted only ONCE, then stopped without trying fallback models
            assert mock_llm.call_count == 1
            assert result.extraction_method == "LOCAL_OCR"
            assert result.fallback_used is True
            assert "401 Unauthorized" in (result.fallback_reason or "")
