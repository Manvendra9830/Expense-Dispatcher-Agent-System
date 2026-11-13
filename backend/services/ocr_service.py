"""
OCR service module.

EasyOCR integration for local text extraction from receipt images.
"""

import numpy as np
from PIL import Image

from backend.utils.config import settings
from backend.utils.logger import get_logger
from backend.utils.exceptions import OCRError

logger = get_logger(__name__)

# Module-level OCR reader (singleton)
_reader = None


def _get_reader():
    """Get or initialize the EasyOCR reader (singleton pattern)."""
    global _reader
    if _reader is None:
        try:
            import easyocr
            languages = [settings.OCR_LANGUAGE]
            logger.info(f"Initializing EasyOCR with languages: {languages}")
            _reader = easyocr.Reader(languages, gpu=False)
            logger.info("EasyOCR reader initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize EasyOCR: {e}")
            raise OCRError(f"Failed to initialize OCR engine: {str(e)}")
    return _reader


def extract_text_from_image(image: Image.Image) -> str:
    """
    Extract text from a PIL Image using EasyOCR.

    Args:
        image: PIL Image instance (RGB).

    Returns:
        Extracted text as a single string.

    Raises:
        OCRError: If text extraction fails.
    """
    try:
        reader = _get_reader()

        # Convert PIL Image to numpy array
        img_array = np.array(image)

        # Run OCR
        results = reader.readtext(img_array, detail=0, paragraph=True)

        # Join all detected text
        text = "\n".join(results)

        if not text.strip():
            logger.warning("OCR produced no text from the image.")
            return ""

        logger.info(f"OCR extracted {len(text)} characters from image.")
        return text

    except OCRError:
        raise
    except Exception as e:
        logger.error(f"OCR extraction failed: {e}")
        raise OCRError(f"Text extraction failed: {str(e)}")


def extract_text_from_pages(pages: list[dict]) -> list[dict]:
    """
    Extract text from multiple PDF pages.

    For each page, if reliable embedded text is available, use it
    instead of running OCR to save processing time.

    Args:
        pages: List of page dicts from preprocessing_service.preprocess_pdf().
               Each dict has 'image', 'text', and 'page_num'.

    Returns:
        Updated list with 'ocr_text' added to each page dict.

    Raises:
        OCRError: If extraction fails.
    """
    for page in pages:
        embedded_text = page.get("text", "")

        # Use embedded text if it's substantial enough
        if len(embedded_text.strip()) > 50:
            page["ocr_text"] = embedded_text
            logger.info(
                f"Page {page['page_num']}: Using embedded PDF text "
                f"({len(embedded_text)} chars)"
            )
        else:
            # Run OCR on the page image
            ocr_text = extract_text_from_image(page["image"])
            page["ocr_text"] = ocr_text
            logger.info(
                f"Page {page['page_num']}: OCR extracted "
                f"{len(ocr_text)} chars"
            )

    return pages


def combine_page_texts(pages: list[dict]) -> str:
    """
    Combine text from multiple pages into a single string.

    Args:
        pages: List of page dicts with 'ocr_text' and 'page_num'.

    Returns:
        Combined text with page markers.
    """
    parts = []
    for page in pages:
        text = page.get("ocr_text", "")
        if text.strip():
            parts.append(f"--- Page {page['page_num']} ---\n{text}")

    return "\n\n".join(parts)

