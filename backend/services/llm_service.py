"""
LLM service module.

OpenRouter Vision LLM integration for structured receipt data extraction.
Supports dynamic model selection and enforces zero-cost / free-tier model safety.
"""

import base64
import json
import time
from typing import Optional

import httpx
from PIL import Image

from backend.services.preprocessing_service import image_to_bytes
from backend.utils.config import settings
from backend.utils.logger import get_logger
from backend.utils.exceptions import (
    LLMError,
    LLMAuthenticationError,
    LLMRateLimitError,
    LLMModelUnavailableError,
)

logger = get_logger(__name__)

# Extraction prompt for the Vision LLM
EXTRACTION_PROMPT = """You are an accurate receipt information extraction system.

Analyze the receipt image and accompanying OCR text.

Extract:

1. Merchant/Store Name.
2. Receipt Date.
3. Line Items:
   - Item Name.
   - Price.
4. Subtotal.
5. Tax.
6. Tip/Gratuity.
7. Total Amount.

Rules:

- Return structured JSON only.
- Do not invent missing information.
- Use null for missing optional values.
- Preserve item names and monetary amounts.
- Distinguish subtotal, tax, tip and total.
- Use the original image to cross-check OCR.
- Flag uncertain information.
- Do not fabricate values to make arithmetic consistent.
- Use ISO date format YYYY-MM-DD when confidently interpretable.

Return ONLY a valid JSON object in this exact format (no markdown, no code fences):
{
  "merchant_name": "string or null",
  "date": "YYYY-MM-DD or null",
  "line_items": [
    {"item_name": "string", "price": "string or null"}
  ],
  "subtotal": "string or null",
  "tax": "string or null",
  "tip": "string or null",
  "total_amount": "string or null",
  "warnings": ["string"]
}"""


RETRY_PROMPT_TEMPLATE = """The previous extraction had validation errors:
{errors}

Please re-examine the receipt image and OCR text, and provide a corrected JSON extraction.
Fix the identified issues while following the same extraction rules.
Return ONLY valid JSON in the same format as before."""


def _encode_image_base64(image: Image.Image) -> str:
    """Encode a PIL Image to base64 string for API transmission."""
    img_bytes = image_to_bytes(image, format="PNG")
    return base64.b64encode(img_bytes).decode("utf-8")


def _build_messages(
    image: Image.Image,
    ocr_text: str,
    retry_errors: Optional[str] = None,
) -> list[dict]:
    """Build the message payload for the OpenRouter API."""
    image_b64 = _encode_image_base64(image)
    user_content = [
        {
            "type": "image_url",
            "image_url": {
                "url": f"data:image/png;base64,{image_b64}",
            },
        }
    ]

    prompt_parts = [EXTRACTION_PROMPT]
    if ocr_text.strip():
        prompt_parts.append(f"\n\nOCR Extracted Text:\n{ocr_text}")
    if retry_errors:
        prompt_parts.append(
            RETRY_PROMPT_TEMPLATE.format(errors=retry_errors)
        )

    user_content.append({
        "type": "text",
        "text": "\n".join(prompt_parts),
    })

    return [{"role": "user", "content": user_content}]


def _call_openrouter(
    messages: list[dict],
    model: Optional[str] = None,
    timeout: Optional[float] = None,
    max_retries: int = 2,
) -> str:
    """
    Make a request to the OpenRouter chat completion API.

    Args:
        messages: Chat messages payload.
        model: Specific model ID to use. Defaults to settings.OPENROUTER_PRIMARY_MODEL.
        timeout: Request timeout in seconds. Defaults to settings.OPENROUTER_TIMEOUT.
        max_retries: Maximum number of retries for transient network/server errors.

    Returns:
        Raw response content string from the LLM.
    """
    target_model = model or settings.OPENROUTER_PRIMARY_MODEL
    req_timeout = timeout or settings.OPENROUTER_TIMEOUT

    # Zero-Cost Protection: strictly disallow paid models if ALLOW_PAID_MODELS is False
    if not settings.ALLOW_PAID_MODELS and not settings.is_free_model(target_model):
        raise LLMError(
            f"Model '{target_model}' rejected: paid inference is disallowed by ALLOW_PAID_MODELS=false."
        )

    if not settings.OPENROUTER_API_KEY or settings.OPENROUTER_API_KEY == "your_openrouter_api_key":
        raise LLMAuthenticationError(
            "OpenRouter API key is not configured. "
            "Set OPENROUTER_API_KEY in your .env file."
        )

    url = f"{settings.OPENROUTER_BASE_URL.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8000",
        "X-Title": "Receipt Extractor",
    }
    payload = {
        "model": target_model,
        "messages": messages,
        "max_tokens": 2048,
        "temperature": 0.1,
    }

    last_error = None
    for attempt in range(max_retries):
        try:
            logger.info(
                f"OpenRouter API call attempt {attempt + 1}/{max_retries} "
                f"(model: {target_model}, timeout: {req_timeout}s)"
            )

            with httpx.Client(timeout=req_timeout) as client:
                response = client.post(url, headers=headers, json=payload)

            # Handle HTTP error statuses
            if response.status_code == 401:
                raise LLMAuthenticationError()
            elif response.status_code == 404:
                raise LLMModelUnavailableError(
                    f"Model '{target_model}' not found or unavailable on OpenRouter."
                )
            elif response.status_code == 429:
                # Do not repeatedly retry 429 to avoid wasting free quota
                raise LLMRateLimitError(
                    f"Free-tier rate limit reached for model '{target_model}'."
                )
            elif response.status_code >= 500:
                if attempt < max_retries - 1:
                    wait_time = 2 ** (attempt + 1)
                    logger.warning(
                        f"Server error ({response.status_code}). "
                        f"Waiting {wait_time}s before retry."
                    )
                    time.sleep(wait_time)
                    continue
                raise LLMError(f"OpenRouter server error: {response.status_code}")
            elif response.status_code != 200:
                raise LLMError(
                    f"OpenRouter API error {response.status_code}: {response.text[:200]}"
                )

            result = response.json()
            if "error" in result:
                error_msg = result["error"].get("message", str(result["error"]))
                raise LLMError(f"OpenRouter API error: {error_msg}")

            choices = result.get("choices", [])
            if not choices:
                raise LLMError("OpenRouter returned no choices in response.")

            content = choices[0].get("message", {}).get("content", "")
            if not content:
                raise LLMError("OpenRouter returned empty content.")

            logger.info(f"OpenRouter response received ({len(content)} chars) from {target_model}")
            return content

        except (LLMAuthenticationError, LLMRateLimitError, LLMModelUnavailableError):
            raise
        except LLMError:
            raise
        except httpx.TimeoutException:
            last_error = f"Request to {target_model} timed out after {req_timeout}s"
            if attempt < max_retries - 1:
                wait_time = 2 ** (attempt + 1)
                logger.warning(f"Timeout on attempt {attempt + 1}. Waiting {wait_time}s...")
                time.sleep(wait_time)
            else:
                raise LLMError(last_error)
        except httpx.ConnectError as e:
            raise LLMError(f"Could not connect to OpenRouter: {str(e)}")
        except Exception as e:
            last_error = str(e)
            if attempt < max_retries - 1:
                wait_time = 2 ** (attempt + 1)
                logger.warning(f"Error: {e}. Waiting {wait_time}s before retry.")
                time.sleep(wait_time)
            else:
                raise LLMError(f"OpenRouter call failed: {str(e)}")

    raise LLMError(f"OpenRouter call failed after {max_retries} attempts: {last_error}")


def extract_receipt_data(
    image: Image.Image,
    ocr_text: str,
    retry_errors: Optional[str] = None,
    model: Optional[str] = None,
) -> str:
    """
    Send receipt image and OCR text to OpenRouter for structured extraction.

    Args:
        image: Preprocessed receipt image.
        ocr_text: OCR-extracted text.
        retry_errors: Validation errors from previous attempt (for self-healing retry).
        model: Specific model ID to use. Defaults to settings.OPENROUTER_PRIMARY_MODEL.

    Returns:
        Raw JSON string from the LLM response.
    """
    messages = _build_messages(image, ocr_text, retry_errors)
    return _call_openrouter(messages, model=model)


def extract_receipt_data_multipage(
    pages: list[dict],
    combined_ocr_text: str,
    retry_errors: Optional[str] = None,
    model: Optional[str] = None,
) -> str:
    """Extract data from a multi-page receipt using primary page image."""
    if not pages:
        raise LLMError("No pages to process.")
    primary_image = pages[0]["image"]
    return extract_receipt_data(primary_image, combined_ocr_text, retry_errors, model=model)
