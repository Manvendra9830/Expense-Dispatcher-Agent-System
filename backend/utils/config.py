"""
Backend utilities - Configuration module.

Centralized configuration loading from environment variables.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
_project_root = Path(__file__).resolve().parent.parent.parent
_env_path = _project_root / ".env"
load_dotenv(dotenv_path=_env_path)


class Settings:
    """Application settings loaded from environment variables."""

    # OpenRouter
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-exp:free")
    OPENROUTER_BASE_URL: str = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./receipts.db")

    # Upload limits
    MAX_UPLOAD_SIZE_MB: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "10"))
    MAX_UPLOAD_SIZE_BYTES: int = MAX_UPLOAD_SIZE_MB * 1024 * 1024
    MAX_PDF_PAGES: int = int(os.getenv("MAX_PDF_PAGES", "5"))

    # OCR
    OCR_LANGUAGE: str = os.getenv("OCR_LANGUAGE", "en")

    # Server
    BACKEND_HOST: str = os.getenv("BACKEND_HOST", "127.0.0.1")
    BACKEND_PORT: int = int(os.getenv("BACKEND_PORT", "8000"))
    FRONTEND_PORT: int = int(os.getenv("FRONTEND_PORT", "8501"))
    BACKEND_BASE_URL: str = os.getenv("BACKEND_BASE_URL", "http://127.0.0.1:8000")

    # Upload directory
    UPLOAD_DIR: Path = Path(__file__).resolve().parent.parent / "uploads"

    # Allowed file extensions
    ALLOWED_EXTENSIONS: set = {".png", ".jpg", ".jpeg", ".pdf"}
    ALLOWED_MIME_TYPES: set = {
        "image/png",
        "image/jpeg",
        "application/pdf",
    }

    @classmethod
    def validate(cls) -> list[str]:
        """Validate required configuration. Returns list of warnings."""
        warnings = []
        if not cls.OPENROUTER_API_KEY or cls.OPENROUTER_API_KEY == "your_openrouter_api_key":
            warnings.append(
                "OPENROUTER_API_KEY is not configured. "
                "LLM extraction will not work until a valid key is set."
            )
        if not cls.OPENROUTER_MODEL:
            warnings.append("OPENROUTER_MODEL is not configured.")
        return warnings

    @classmethod
    def ensure_directories(cls) -> None:
        """Create necessary directories if they don't exist."""
        cls.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


settings = Settings()

