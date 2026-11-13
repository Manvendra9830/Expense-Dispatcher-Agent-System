"""
Extraction service module.

Orchestrates the complete receipt extraction pipeline:
file processing → OCR → LLM → parsing → validation → persistence.
"""

import json
import traceback
from typing import Optional

from PIL import Image
from sqlalchemy.orm import Session

from backend.services.file_service import validate_file, save_file
from backend.services.preprocessing_service import (
    preprocess_image,
    preprocess_pdf,
    image_to_bytes,
)
from backend.services.ocr_service import (
    extract_text_from_image,
    extract_text_from_pages,
    combine_page_texts,
)
from backend.services.llm_service import (
    extract_receipt_data,
    extract_receipt_data_multipage,
)
from backend.services.validation_service import validate_extraction, determine_status
from backend.database.repository import create_receipt, create_failed_receipt
from backend.database.models import Receipt
from backend.schemas.receipt_schema import ReceiptExtraction
from backend.utils.logger import get_logger
from backend.utils.exceptions import (
    ReceiptExtractorError,
    ExtractionError,
    LLMError,
)

logger = get_logger(__name__)


def _parse_llm_response(raw_response: str) -> dict:
    """
    Parse the LLM JSON response, handling common formatting issues.

    Args:
        raw_response: Raw string response from the LLM.

    Returns:
        Parsed dictionary.

    Raises:
        ExtractionError: If JSON parsing fails.
    """
    # Strip markdown code fences if present
    text = raw_response.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    # Try direct JSON parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find JSON object in the text
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass

    raise ExtractionError(
        f"Could not parse LLM response as JSON. "
        f"Response starts with: {raw_response[:200]}"
    )


def process_receipt(
    filename: str,
    content: bytes,
    db: Session,
) -> Receipt:
    """
    Process a receipt file through the full extraction pipeline.

    Pipeline:
    1. Validate file.
    2. Save file.
    3. Preprocess image/PDF.
    4. Run OCR.
    5. Call LLM for structured extraction.
    6. Parse LLM response.
    7. Validate extraction.
    8. Persist to database.

    Args:
        filename: Original uploaded filename.
        content: File content as bytes.
        db: Database session.

    Returns:
        Receipt database model instance.

    Raises:
        ReceiptExtractorError: If any step fails critically.
    """
    # Step 1: Validate file
    mime_type = validate_file(filename, content)
    logger.info(f"Processing receipt: {filename} ({mime_type})")

    # Step 2: Save file
    unique_filename, file_path = save_file(filename, content)

    # Step 3 & 4: Preprocess and OCR
    ocr_text = ""
    primary_image: Optional[Image.Image] = None

    try:
        if mime_type in ("image/png", "image/jpeg"):
            # Image processing
            primary_image = preprocess_image(content)
            ocr_text = extract_text_from_image(primary_image)

        elif mime_type == "application/pdf":
            # PDF processing
            pages = preprocess_pdf(content)
            pages = extract_text_from_pages(pages)
            ocr_text = combine_page_texts(pages)
            # Use first page image as primary
            if pages:
                primary_image = pages[0]["image"]

    except ReceiptExtractorError:
        raise
    except Exception as e:
        logger.error(f"Preprocessing/OCR failed: {e}")
        # Save as failed receipt
        receipt = create_failed_receipt(
            db=db,
            filename=unique_filename,
            file_path=str(file_path),
            status="FAILED",
        )
        raise

    # Step 5: LLM extraction
    try:
        if primary_image is None:
            raise ExtractionError("No image available for LLM processing.")

        raw_response = extract_receipt_data(primary_image, ocr_text)
        logger.info("LLM extraction completed.")

    except LLMError as e:
        logger.error(f"LLM extraction failed: {e}")
        # Save with OCR text but mark as failed
        receipt = create_failed_receipt(
            db=db,
            filename=unique_filename,
            file_path=str(file_path),
            raw_ocr_text=ocr_text,
            status="FAILED",
        )
        raise

    # Step 6: Parse LLM response
    try:
        extracted_data = _parse_llm_response(raw_response)
    except ExtractionError as e:
        logger.error(f"JSON parsing failed: {e}")
        receipt = create_failed_receipt(
            db=db,
            filename=unique_filename,
            file_path=str(file_path),
            raw_ocr_text=ocr_text,
            status="FAILED",
            extracted_json=raw_response[:2000],
        )
        raise

    # Step 7: Pydantic validation
    try:
        extraction = ReceiptExtraction(**extracted_data)
    except Exception as e:
        logger.warning(f"First Pydantic validation failed: {e}")

        # Retry LLM with validation feedback
        try:
            retry_response = extract_receipt_data(
                primary_image, ocr_text, retry_errors=str(e)
            )
            retry_data = _parse_llm_response(retry_response)
            extraction = ReceiptExtraction(**retry_data)
            logger.info("Retry extraction succeeded.")
        except Exception as retry_e:
            logger.error(f"Retry extraction also failed: {retry_e}")
            receipt = create_failed_receipt(
                db=db,
                filename=unique_filename,
                file_path=str(file_path),
                raw_ocr_text=ocr_text,
                status="REVIEW_REQUIRED",
                extracted_json=json.dumps(extracted_data),
            )
            raise ExtractionError(
                f"Could not validate extraction after retry: {str(retry_e)}"
            )

    # Step 8: Business validation
    extraction = validate_extraction(extraction)
    status = determine_status(extraction)

    # Step 9: Persist to database
    receipt = create_receipt(
        db=db,
        filename=unique_filename,
        file_path=str(file_path),
        extraction=extraction,
        raw_ocr_text=ocr_text,
        status=status,
    )

    logger.info(
        f"Receipt processed successfully: ID={receipt.id}, "
        f"merchant='{receipt.merchant_name}', status={status}"
    )
    return receipt

