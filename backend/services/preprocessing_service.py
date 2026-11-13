"""
Preprocessing service module.

Handles image and PDF preprocessing for OCR and LLM input.
"""

import io
from pathlib import Path

from PIL import Image, ExifTags
import fitz  # PyMuPDF

from backend.utils.logger import get_logger
from backend.utils.exceptions import FileProcessingError

logger = get_logger(__name__)

# Maximum dimension for resizing
MAX_DIMENSION = 2048


def preprocess_image(content: bytes) -> Image.Image:
    """
    Preprocess an image for OCR and LLM processing.

    Operations:
    - Convert to RGB.
    - Correct orientation from EXIF data.
    - Resize if too large.

    Args:
        content: Raw image bytes.

    Returns:
        Preprocessed PIL Image.

    Raises:
        FileProcessingError: If preprocessing fails.
    """
    try:
        img = Image.open(io.BytesIO(content))

        # Correct orientation from EXIF
        try:
            exif = img._getexif()
            if exif:
                orientation_key = None
                for key, val in ExifTags.TAGS.items():
                    if val == "Orientation":
                        orientation_key = key
                        break
                if orientation_key and orientation_key in exif:
                    orientation = exif[orientation_key]
                    if orientation == 3:
                        img = img.rotate(180, expand=True)
                    elif orientation == 6:
                        img = img.rotate(270, expand=True)
                    elif orientation == 8:
                        img = img.rotate(90, expand=True)
        except (AttributeError, KeyError):
            pass  # No EXIF data

        # Convert to RGB
        if img.mode != "RGB":
            img = img.convert("RGB")

        # Resize if too large
        width, height = img.size
        if max(width, height) > MAX_DIMENSION:
            ratio = MAX_DIMENSION / max(width, height)
            new_size = (int(width * ratio), int(height * ratio))
            img = img.resize(new_size, Image.LANCZOS)
            logger.info(f"Image resized from {width}x{height} to {new_size[0]}x{new_size[1]}")

        logger.info(f"Image preprocessed: {img.size[0]}x{img.size[1]} RGB")
        return img

    except Exception as e:
        logger.error(f"Image preprocessing failed: {e}")
        raise FileProcessingError(f"Failed to preprocess image: {str(e)}")


def preprocess_pdf(content: bytes, max_pages: int = 5) -> list[dict]:
    """
    Preprocess a PDF by converting pages to images and extracting embedded text.

    Args:
        content: Raw PDF bytes.
        max_pages: Maximum pages to process.

    Returns:
        List of dicts with 'image' (PIL Image), 'text' (embedded text),
        and 'page_num' (1-based page number).

    Raises:
        FileProcessingError: If preprocessing fails.
    """
    try:
        doc = fitz.open(stream=content, filetype="pdf")
        pages = []

        for page_num in range(min(len(doc), max_pages)):
            page = doc[page_num]

            # Extract embedded selectable text
            embedded_text = page.get_text("text").strip()

            # Convert page to image
            # Use a high DPI for better OCR quality
            mat = fitz.Matrix(2.0, 2.0)  # 2x zoom ≈ 144 DPI
            pix = page.get_pixmap(matrix=mat)

            # Convert pixmap to PIL Image
            img_data = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_data))
            if img.mode != "RGB":
                img = img.convert("RGB")

            pages.append({
                "image": img,
                "text": embedded_text,
                "page_num": page_num + 1,
            })

            logger.info(
                f"PDF page {page_num + 1}: "
                f"{img.size[0]}x{img.size[1]}, "
                f"embedded text: {len(embedded_text)} chars"
            )

        doc.close()
        logger.info(f"PDF preprocessed: {len(pages)} pages")
        return pages

    except Exception as e:
        logger.error(f"PDF preprocessing failed: {e}")
        raise FileProcessingError(f"Failed to preprocess PDF: {str(e)}")


def image_to_bytes(img: Image.Image, format: str = "PNG") -> bytes:
    """
    Convert a PIL Image to bytes.

    Args:
        img: PIL Image instance.
        format: Output format (PNG, JPEG).

    Returns:
        Image as bytes.
    """
    buffer = io.BytesIO()
    img.save(buffer, format=format)
    buffer.seek(0)
    return buffer.read()

