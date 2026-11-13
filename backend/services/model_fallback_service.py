"""
Model fallback service module.

Coordinates sequential free Vision model fallback and local OCR fallback.
Order of execution:
1. Primary free Vision model (e.g. nvidia/nemotron-3.5-super-vl:free)
2. Verified fallback free Vision models (e.g. google/gemma-4-31b-it:free, particle-ai/particle-1:free)
3. Local OCR Parser (zero-network heuristic extraction)
"""

import json
from dataclasses import dataclass
from typing import Optional
from PIL import Image

from backend.schemas.receipt_schema import ReceiptExtraction
from backend.services.llm_service import extract_receipt_data
from backend.services.local_receipt_parser import parse_receipt_text_locally
from backend.services.quota_service import is_account_quota_exhausted
from backend.utils.config import settings
from backend.utils.logger import get_logger
from backend.utils.exceptions import (
    LLMAuthenticationError,
    LLMRateLimitError,
    LLMModelUnavailableError,
    LLMError,
    ExtractionError,
)

logger = get_logger(__name__)


@dataclass
class FallbackExtractionResult:
    """Encapsulates the extraction output and execution metadata."""

    extraction: ReceiptExtraction
    model_used: Optional[str]
    extraction_method: str  # "AI" or "LOCAL_OCR"
    fallback_used: bool
    fallback_reason: Optional[str] = None


def parse_llm_json(raw_response: str) -> dict:
    """Parse JSON string from LLM response, stripping markdown fences if present."""
    text = raw_response.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Search for first { and last }
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass

    raise ExtractionError(f"Could not parse LLM output as JSON: {raw_response[:200]}")


def extract_with_fallback(
    image: Image.Image,
    ocr_text: str,
) -> FallbackExtractionResult:
    """
    Execute extraction with sequential model fallback and local OCR safety net.

    Args:
        image: Preprocessed receipt image.
        ocr_text: Preprocessed text from EasyOCR.

    Returns:
        FallbackExtractionResult containing validated extraction and metadata.
    """
    # Check if OpenRouter key is configured
    if not settings.OPENROUTER_API_KEY or settings.OPENROUTER_API_KEY == "your_openrouter_api_key":
        logger.info("OpenRouter API key is not configured. Falling back to local OCR parser.")
        local_extraction = parse_receipt_text_locally(ocr_text)
        return FallbackExtractionResult(
            extraction=local_extraction,
            model_used=None,
            extraction_method="LOCAL_OCR",
            fallback_used=True,
            fallback_reason="OpenRouter API key not configured.",
        )

    # Check account quota before attempting network inference
    if is_account_quota_exhausted():
        logger.warning("Account quota is exhausted. Falling back to local OCR parser immediately.")
        local_extraction = parse_receipt_text_locally(ocr_text)
        return FallbackExtractionResult(
            extraction=local_extraction,
            model_used=None,
            extraction_method="LOCAL_OCR",
            fallback_used=True,
            fallback_reason="Account-wide free quota exhausted.",
        )

    # Compile candidate models: primary model followed by up to 2 fallback models
    candidate_models = settings.get_all_configured_models()

    # Zero-Cost Safety: Filter out any non-free models if ALLOW_PAID_MODELS is False
    if not settings.ALLOW_PAID_MODELS:
        candidate_models = [m for m in candidate_models if settings.is_free_model(m)]

    if not candidate_models:
        logger.warning("No verified free models configured. Falling back to local OCR parser.")
        local_extraction = parse_receipt_text_locally(ocr_text)
        return FallbackExtractionResult(
            extraction=local_extraction,
            model_used=None,
            extraction_method="LOCAL_OCR",
            fallback_used=True,
            fallback_reason="No verified free models available in configuration.",
        )

    primary_model = candidate_models[0]
    failure_reasons: list[str] = []

    for index, model_id in enumerate(candidate_models):
        is_fallback_attempt = (index > 0)
        logger.info(
            f"Attempting extraction using model [{index + 1}/{len(candidate_models)}]: '{model_id}' "
            f"(fallback={is_fallback_attempt})"
        )

        try:
            raw_response = extract_receipt_data(image, ocr_text, model=model_id)
            extracted_dict = parse_llm_json(raw_response)

            try:
                extraction = ReceiptExtraction(**extracted_dict)
            except Exception as schema_err:
                logger.warning(
                    f"First validation failed for {model_id}: {schema_err}. Attempting self-healing retry..."
                )
                retry_response = extract_receipt_data(
                    image, ocr_text, retry_errors=str(schema_err), model=model_id
                )
                retry_dict = parse_llm_json(retry_response)
                extraction = ReceiptExtraction(**retry_dict)

            # Successfully extracted and validated via AI
            logger.info(f"Extraction successful using model: {model_id}")
            return FallbackExtractionResult(
                extraction=extraction,
                model_used=model_id,
                extraction_method="AI",
                fallback_used=is_fallback_attempt,
                fallback_reason="; ".join(failure_reasons) if failure_reasons else None,
            )

        except LLMAuthenticationError as e:
            # 401 Unauthorized: API key is invalid. Stop ALL AI attempts immediately.
            logger.error(f"Authentication error with OpenRouter API: {e}. Stopping AI calls.")
            failure_reasons.append(f"{model_id}: 401 Unauthorized")
            break

        except (LLMModelUnavailableError, LLMRateLimitError, LLMError, ExtractionError) as e:
            reason = f"{model_id} failed: {str(e)}"
            logger.warning(f"{reason}. Proceeding to fallback...")
            failure_reasons.append(reason)
            continue

        except Exception as e:
            reason = f"{model_id} unexpected error: {str(e)}"
            logger.error(reason)
            failure_reasons.append(reason)
            continue

    # If all AI models failed or authentication failed, activate local OCR parser
    combined_reasons = "; ".join(failure_reasons) if failure_reasons else "All AI models failed."
    logger.warning(
        f"All AI extraction attempts failed ({combined_reasons}). Activating Local OCR Parser..."
    )
    local_extraction = parse_receipt_text_locally(ocr_text)

    return FallbackExtractionResult(
        extraction=local_extraction,
        model_used=None,
        extraction_method="LOCAL_OCR",
        fallback_used=True,
        fallback_reason=combined_reasons,
    )

