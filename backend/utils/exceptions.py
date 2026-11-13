"""
Backend utilities - Custom exceptions module.

Centralized exception classes for structured error handling.
"""


class ReceiptExtractorError(Exception):
    """Base exception for the receipt extractor application."""

    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class FileValidationError(ReceiptExtractorError):
    """Raised when file validation fails."""

    def __init__(self, message: str):
        super().__init__(message=message, status_code=400)


class FileProcessingError(ReceiptExtractorError):
    """Raised when file processing fails."""

    def __init__(self, message: str):
        super().__init__(message=message, status_code=422)


class OCRError(ReceiptExtractorError):
    """Raised when OCR processing fails."""

    def __init__(self, message: str):
        super().__init__(message=message, status_code=422)


class LLMError(ReceiptExtractorError):
    """Raised when LLM inference fails."""

    def __init__(self, message: str):
        super().__init__(message=message, status_code=502)


class LLMAuthenticationError(LLMError):
    """Raised when LLM API credentials are invalid."""

    def __init__(self, message: str = "Invalid or missing OpenRouter API key."):
        super().__init__(message=message)


class LLMRateLimitError(LLMError):
    """Raised when LLM API rate limit is exceeded."""

    def __init__(self, message: str = "OpenRouter rate limit exceeded. Please try again later."):
        super().__init__(message=message)


class LLMModelUnavailableError(LLMError):
    """Raised when the requested LLM model is unavailable."""

    def __init__(self, message: str = "The configured LLM model is unavailable."):
        super().__init__(message=message)


class ExtractionError(ReceiptExtractorError):
    """Raised when data extraction from LLM response fails."""

    def __init__(self, message: str):
        super().__init__(message=message, status_code=422)


class ValidationError(ReceiptExtractorError):
    """Raised when business validation fails."""

    def __init__(self, message: str):
        super().__init__(message=message, status_code=422)


class DatabaseError(ReceiptExtractorError):
    """Raised when database operations fail."""

    def __init__(self, message: str):
        super().__init__(message=message, status_code=500)


class ReceiptNotFoundError(ReceiptExtractorError):
    """Raised when a receipt is not found."""

    def __init__(self, receipt_id: int):
        super().__init__(
            message=f"Receipt with ID {receipt_id} not found.",
            status_code=404,
        )

