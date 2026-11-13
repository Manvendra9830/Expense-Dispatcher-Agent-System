"""
File service module.

Handles file validation, saving, and management.
"""

import mimetypes
import uuid
from pathlib import Path

from PIL import Image
import fitz  # PyMuPDF

from backend.utils.config import settings
from backend.utils.logger import get_logger
from backend.utils.exceptions import FileValidationError, FileProcessingError

logger = get_logger(__name__)


def validate_file(filename: str, content: bytes) -> str:
    """
    Validate an uploaded file.

    Args:
        filename: Original filename.
        content: File content as bytes.

    Returns:
        Detected MIME type string.

    Raises:
        FileValidationError: If validation fails.
    """
    if not filename:
        raise FileValidationError("No filename provided.")

    # Check extension
    ext = Path(filename).suffix.lower()
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise FileValidationError(
            f"Unsupported file type '{ext}'. "
            f"Allowed: {', '.join(settings.ALLOWED_EXTENSIONS)}"
        )

    # Check file size
    file_size = len(content)
    if file_size == 0:
        raise FileValidationError("Uploaded file is empty.")
    if file_size > settings.MAX_UPLOAD_SIZE_BYTES:
        raise FileValidationError(
            f"File too large ({file_size / (1024*1024):.1f} MB). "
            f"Maximum: {settings.MAX_UPLOAD_SIZE_MB} MB."
        )

    # Check MIME type
    mime_type, _ = mimetypes.guess_type(filename)
    if mime_type not in settings.ALLOWED_MIME_TYPES:
        # Try to detect from content
        if content[:8] == b'\x89PNG\r\n\x1a\n':
            mime_type = "image/png"
        elif content[:3] == b'\xff\xd8\xff':
            mime_type = "image/jpeg"
        elif content[:5] == b'%PDF-':
            mime_type = "application/pdf"
        else:
            raise FileValidationError(
                f"Could not determine file type for '{filename}'. "
                f"Allowed types: PNG, JPG, JPEG, PDF."
            )

    # Validate file integrity
    try:
        if mime_type in ("image/png", "image/jpeg"):
            img = Image.open(__import__("io").BytesIO(content))
            img.verify()
        elif mime_type == "application/pdf":
            doc = fitz.open(stream=content, filetype="pdf")
            page_count = len(doc)
            doc.close()
            if page_count == 0:
                raise FileValidationError("PDF has no pages.")
            if page_count > settings.MAX_PDF_PAGES:
                raise FileValidationError(
                    f"PDF has {page_count} pages. Maximum: {settings.MAX_PDF_PAGES}."
                )
    except FileValidationError:
        raise
    except Exception as e:
        raise FileValidationError(f"File appears to be corrupted: {str(e)}")

    logger.info(f"File validated: {filename} ({mime_type}, {file_size} bytes)")
    return mime_type


def save_file(filename: str, content: bytes) -> tuple[str, Path]:
    """
    Save uploaded file with a unique name.

    Args:
        filename: Original filename.
        content: File content as bytes.

    Returns:
        Tuple of (unique_filename, file_path).

    Raises:
        FileProcessingError: If saving fails.
    """
    try:
        settings.ensure_directories()
        ext = Path(filename).suffix.lower()
        unique_name = f"{uuid.uuid4().hex}{ext}"
        file_path = settings.UPLOAD_DIR / unique_name

        file_path.write_bytes(content)
        logger.info(f"File saved: {unique_name} at {file_path}")
        return unique_name, file_path

    except Exception as e:
        logger.error(f"Failed to save file: {e}")
        raise FileProcessingError(f"Failed to save uploaded file: {str(e)}")

