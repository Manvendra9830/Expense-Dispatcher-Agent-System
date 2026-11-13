"""
LLM service module.

OpenRouter Vision LLM integration for structured receipt data extraction.
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
    """
    Encode a PIL Image to base64 string for API transmission.

    Args:
        image: PIL Image instance.

    Returns:
        Base64 encoded string.
    """
    img_bytes = image_to_bytes(image, format="PNG")
    return base64.b64encode(img_bytes).decode("utf-8")


def _build_messages(
    image: Image.Image,
    ocr_text: str,
    retry_errors: Optional[str] = None,
) -> list[dict]:
    """
    Build the message payload for the OpenRouter API.

    Args:
        image: Receipt image.
        ocr_text: OCR-extracted text.
        retry_errors: Validation errors from a previous attempt (for retry).

    Returns:
        List of message dicts for the chat completion API.
    """
    image_b64 = _encode_image_base64(image)

    user_content = []

    # Add receipt image
    user_content.append({
        "type": "image_url",
        "image_url": {
            "url": f"data:image/png;base64,{image_b64}",
        },
    })

    # Build text prompt
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

    return [
        {"role": "user", "content": user_content}
    ]


def _call_openrouter(
    messages: list[dict],
    timeout: float = 60.0,
    max_retries: int = 3,
) -> str:
    """
    Make a request to the OpenRouter chat completion API with retry logic.

    Args:
        messages: Chat messages payload.
        timeout: Request timeout in seconds.
        max_retries: Maximum number of retries for transient failures.

    Returns:
        Raw response content string from the LLM.

    Raises:
        LLMAuthenticationError: If API key is invalid.
        LLMRateLimitError: If rate limit is exceeded.
        LLMModelUnavailableError: If model is unavailable.
        LLMError: For other failures.
    """
    if not settings.OPENROUTER_API_KEY or settings.OPENROUTER_API_KEY == "your_openrouter_api_key":
        raise LLMAuthenticationError(
            "OpenRouter API key is not configured. "
            "Set OPENROUTER_API_KEY in your .env file."
        )

    url = f"{settings.OPENROUTER_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8000",
        "X-Title": "Receipt Extractor",
    }
    payload = {
        "model": settings.OPENROUTER_MODEL,
        "messages": messages,
        "max_tokens": 2048,
        "temperature": 0.1,
    }

    last_error = None
    for attempt in range(max_retries):
        try:
            logger.info(
                f"OpenRouter API call attempt {attempt + 1}/{max_retries} "
                f"(model: {settings.OPENROUTER_MODEL})"
            )

            with httpx.Client(timeout=timeout) as client:
                response = client.post(url, headers=headers, json=payload)

            # Handle HTTP errors
            if response.status_code == 401:
                raise LLMAuthenticationError()
            elif response.status_code == 429:
                if attempt < max_retries - 1:
                    wait_time = 2 ** (attempt + 1)
                    logger.warning(f"Rate limited. Waiting {wait_time}s before retry.")
                    time.sleep(wait_time)
                    continue
                raise LLMRateLimitError()
            elif response.status_code == 404:
                raise LLMModelUnavailableError(
                    f"Model '{settings.OPENROUTER_MODEL}' not found on OpenRouter."
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
                    f"OpenRouter API error: {response.status_code} - {response.text[:200]}"
                )

            # Parse response
            result = response.json()

            # Check for API-level errors
            if "error" in result:
                error_msg = result["error"].get("message", str(result["error"]))
                raise LLMError(f"OpenRouter API error: {error_msg}")

            # Extract content
            choices = result.get("choices", [])
            if not choices:
                raise LLMError("OpenRouter returned no choices.")

            content = choices[0].get("message", {}).get("content", "")
            if not content:
                raise LLMError("OpenRouter returned empty content.")

            logger.info(f"OpenRouter response received ({len(content)} chars)")
            return content

        except (LLMAuthenticationError, LLMRateLimitError, LLMModelUnavailableError):
            raise
        except LLMError:
            last_error = e if 'e' in dir() else None
            raise
        except httpx.TimeoutException:
            last_error = "Request timed out"
            if attempt < max_retries - 1:
                wait_time = 2 ** (attempt + 1)
                logger.warning(f"Timeout. Waiting {wait_time}s before retry.")
                time.sleep(wait_time)
            else:
                raise LLMError(
                    f"OpenRouter request timed out after {max_retries} attempts."
                )
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
) -> str:
    """
    Send a receipt image and OCR text to OpenRouter for structured extraction.

    Args:
        image: Preprocessed receipt image.
        ocr_text: OCR-extracted text.
        retry_errors: Validation errors from a previous attempt (for retry).

    Returns:
        Raw JSON string from the LLM response.

    Raises:
        LLMError: If extraction fails.
    """
    messages = _build_messages(image, ocr_text, retry_errors)
    return _call_openrouter(messages)


def extract_receipt_data_multipage(
    pages: list[dict],
    combined_ocr_text: str,
    retry_errors: Optional[str] = None,
) -> str:
    """
    Extract data from a multi-page receipt.

    Sends the first page image with combined OCR text from all pages.

    Args:
        pages: List of page dicts with 'image' and 'ocr_text'.
        combined_ocr_text: Combined OCR text from all pages.
        retry_errors: Validation errors from a previous attempt.

    Returns:
        Raw JSON string from the LLM response.

    Raises:
        LLMError: If extraction fails.
    """
    if not pages:
        raise LLMError("No pages to process.")

    # Use the first page's image as the primary image
    primary_image = pages[0]["image"]

    return extract_receipt_data(primary_image, combined_ocr_text, retry_errors)

