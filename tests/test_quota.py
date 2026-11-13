"""
Unit tests for the OpenRouter quota monitoring service.
Uses mocked HTTP responses; zero external credits used.
"""

from unittest.mock import patch, MagicMock
import pytest

from backend.services.quota_service import check_quota, is_account_quota_exhausted, QuotaStatus


class TestQuotaService:
    """Tests for OpenRouter key and quota monitoring."""

    @patch("backend.services.quota_service.httpx.Client")
    def test_quota_available_free_tier(self, mock_client_class):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "label": "test-key",
                "limit": None,
                "usage": 0.0,
                "limit_remaining": None,
                "is_free_tier": True,
            }
        }
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        with patch("backend.services.quota_service.settings") as mock_settings:
            mock_settings.OPENROUTER_API_KEY = "sk-test"
            mock_settings.OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
            mock_settings.QUOTA_CACHE_TTL_SECONDS = 0  # no cache for test

            status = check_quota(force_refresh=True)
            assert status.is_valid is True
            assert status.is_free_tier is True
            assert status.is_exhausted is False

    @patch("backend.services.quota_service.httpx.Client")
    def test_quota_exhausted(self, mock_client_class):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "label": "test-key",
                "limit": 10.0,
                "usage": 10.0,
                "limit_remaining": 0.0,
                "is_free_tier": True,
            }
        }
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        with patch("backend.services.quota_service.settings") as mock_settings:
            mock_settings.OPENROUTER_API_KEY = "sk-test"
            mock_settings.OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
            mock_settings.QUOTA_CACHE_TTL_SECONDS = 0

            status = check_quota(force_refresh=True)
            assert status.is_exhausted is True

    @patch("backend.services.quota_service.httpx.Client")
    def test_quota_auth_error_401(self, mock_client_class):
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        with patch("backend.services.quota_service.settings") as mock_settings:
            mock_settings.OPENROUTER_API_KEY = "sk-invalid"
            mock_settings.OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
            mock_settings.QUOTA_CACHE_TTL_SECONDS = 0

            status = check_quota(force_refresh=True)
            assert status.is_valid is False
            assert status.is_exhausted is True
            assert "Invalid" in status.error_message

    def test_quota_unconfigured_key(self):
        with patch("backend.services.quota_service.settings") as mock_settings:
            mock_settings.OPENROUTER_API_KEY = ""
            status = check_quota(force_refresh=True)
            assert status.is_configured is False
            assert status.is_exhausted is True

    @patch("backend.services.quota_service.httpx.Client")
    def test_quota_caching(self, mock_client_class):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"usage": 5.0, "is_free_tier": True}}
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        with patch("backend.services.quota_service.settings") as mock_settings:
            mock_settings.OPENROUTER_API_KEY = "sk-test"
            mock_settings.OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
            mock_settings.QUOTA_CACHE_TTL_SECONDS = 60

            # First call: live
            res1 = check_quota(force_refresh=True)
            assert res1.cached is False

            # Second call: cached
            res2 = check_quota(force_refresh=False)
            assert res2.cached is True
            assert res2.usage == 5.0
