"""
Quota service module.

Monitors OpenRouter account status, credit usage, and free-tier rate limits
via the OpenRouter Key endpoint (GET https://openrouter.ai/api/v1/key).
Caches results for a configurable TTL to prevent unnecessary network overhead.
"""

import time
from typing import Optional
from dataclasses import dataclass
import httpx

from backend.utils.config import settings
from backend.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class QuotaStatus:
    """Represents current OpenRouter key and quota status."""

    is_configured: bool
    is_valid: bool
    is_free_tier: bool
    usage: float = 0.0
    limit: Optional[float] = None
    limit_remaining: Optional[float] = None
    is_exhausted: bool = False
    rate_limit_info: Optional[dict] = None
    cached: bool = False
    error_message: Optional[str] = None


# Module-level cache for quota status
_cached_quota: Optional[QuotaStatus] = None
_cache_timestamp: float = 0.0


def check_quota(force_refresh: bool = False) -> QuotaStatus:
    """
    Retrieve current OpenRouter key quota status.

    Uses an in-memory cache with TTL defined in settings.QUOTA_CACHE_TTL_SECONDS.

    Args:
        force_refresh: If True, bypass the cache and fetch live status.

    Returns:
        QuotaStatus instance.
    """
    global _cached_quota, _cache_timestamp

    if not settings.OPENROUTER_API_KEY or settings.OPENROUTER_API_KEY == "your_openrouter_api_key":
        return QuotaStatus(
            is_configured=False,
            is_valid=False,
            is_free_tier=True,
            is_exhausted=True,
            error_message="OpenRouter API key is not configured.",
        )

    now = time.time()
    if (
        not force_refresh
        and _cached_quota is not None
        and (now - _cache_timestamp) < settings.QUOTA_CACHE_TTL_SECONDS
    ):
        return QuotaStatus(
            is_configured=_cached_quota.is_configured,
            is_valid=_cached_quota.is_valid,
            is_free_tier=_cached_quota.is_free_tier,
            usage=_cached_quota.usage,
            limit=_cached_quota.limit,
            limit_remaining=_cached_quota.limit_remaining,
            is_exhausted=_cached_quota.is_exhausted,
            rate_limit_info=_cached_quota.rate_limit_info,
            cached=True,
            error_message=_cached_quota.error_message,
        )

    url = f"{settings.OPENROUTER_BASE_URL.rstrip('/')}/key"
    headers = {
        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
        "HTTP-Referer": "http://localhost:8000",
        "X-Title": "Receipt Extractor",
    }

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(url, headers=headers)

        if response.status_code == 401:
            logger.warning("OpenRouter API key validation failed (401 Unauthorized).")
            status = QuotaStatus(
                is_configured=True,
                is_valid=False,
                is_free_tier=True,
                is_exhausted=True,
                error_message="Invalid OpenRouter API key.",
            )
        elif response.status_code == 200:
            data = response.json().get("data", {})
            usage = float(data.get("usage") or 0.0)
            limit = data.get("limit")
            limit_remaining = data.get("limit_remaining")
            is_free_tier = bool(data.get("is_free_tier", True))
            rate_limit = data.get("rate_limit")

            # Check if limit is explicitly exhausted (e.g. limit_remaining is 0 or usage >= limit)
            is_exhausted = False
            if limit_remaining is not None and float(limit_remaining) <= 0:
                is_exhausted = True
            elif limit is not None and usage >= float(limit):
                is_exhausted = True

            status = QuotaStatus(
                is_configured=True,
                is_valid=True,
                is_free_tier=is_free_tier,
                usage=usage,
                limit=float(limit) if limit is not None else None,
                limit_remaining=float(limit_remaining) if limit_remaining is not None else None,
                is_exhausted=is_exhausted,
                rate_limit_info=rate_limit,
                cached=False,
            )
            logger.info(
                f"Quota check: is_free_tier={is_free_tier}, usage={usage}, "
                f"remaining={limit_remaining}, exhausted={is_exhausted}"
            )
        else:
            logger.warning(
                f"OpenRouter /key check returned status {response.status_code}. "
                "Assuming quota is intact for controlled attempt."
            )
            status = QuotaStatus(
                is_configured=True,
                is_valid=True,
                is_free_tier=True,
                is_exhausted=False,
                error_message=f"Key endpoint returned {response.status_code}",
            )

    except Exception as e:
        logger.warning(f"Failed to query OpenRouter quota endpoint: {e}")
        status = QuotaStatus(
            is_configured=True,
            is_valid=True,
            is_free_tier=True,
            is_exhausted=False,
            error_message=f"Quota endpoint unreachable: {str(e)}",
        )

    _cached_quota = status
    _cache_timestamp = now
    return status


def is_account_quota_exhausted() -> bool:
    """Return whether the account-wide quota is known to be exhausted."""
    if not settings.ENABLE_QUOTA_MONITORING:
        return False
    quota = check_quota()
    return quota.is_exhausted

