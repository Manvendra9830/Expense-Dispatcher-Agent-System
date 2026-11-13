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

    # Project Root and Paths
    PROJECT_ROOT: Path = _project_root
    UPLOAD_DIR: Path = Path(__file__).resolve().parent.parent / "uploads"
    EASYOCR_MODEL_DIR: Path = _project_root / "models" / "easyocr"

    # OpenRouter API Configuration
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_BASE_URL: str = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

    # Primary and Fallback Models (Phase 2)
    # Backward compatibility: fall back to OPENROUTER_MODEL if OPENROUTER_PRIMARY_MODEL is unset
    OPENROUTER_PRIMARY_MODEL: str = (
        os.getenv("OPENROUTER_PRIMARY_MODEL")
        or os.getenv("OPENROUTER_MODEL")
        or "nvidia/nemotron-3.5-super-vl:free"
    )
    # Backward compatibility alias
    OPENROUTER_MODEL: str = OPENROUTER_PRIMARY_MODEL

    # Fallback free Vision models (comma-separated)
    _raw_fallback: str = os.getenv(
        "OPENROUTER_FALLBACK_MODELS",
        "google/gemma-4-31b-it:free,particle-ai/particle-1:free",
    )
    OPENROUTER_FALLBACK_MODELS: list[str] = [
        m.strip() for m in _raw_fallback.split(",") if m.strip()
    ]

    # Zero-Cost Protection: strictly disallow paid models
    ALLOW_PAID_MODELS: bool = os.getenv("ALLOW_PAID_MODELS", "false").lower() in (
        "true",
        "1",
        "yes",
    )

    # Quota Monitoring Configuration
    ENABLE_QUOTA_MONITORING: bool = os.getenv("ENABLE_QUOTA_MONITORING", "true").lower() in (
        "true",
        "1",
        "yes",
    )
    QUOTA_CACHE_TTL_SECONDS: int = int(os.getenv("QUOTA_CACHE_TTL_SECONDS", "60"))

    # Timeouts
    OPENROUTER_TIMEOUT: float = float(os.getenv("OPENROUTER_TIMEOUT", "90.0"))
    HTTP_REQUEST_TIMEOUT: float = float(os.getenv("HTTP_REQUEST_TIMEOUT", "300.0"))

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

    # Allowed file extensions
    ALLOWED_EXTENSIONS: set = {".png", ".jpg", ".jpeg", ".pdf"}
    ALLOWED_MIME_TYPES: set = {
        "image/png",
        "image/jpeg",
        "application/pdf",
    }

    @classmethod
    def get_all_configured_models(cls) -> list[str]:
        """Return unique ordered list of all configured free models."""
        models = [cls.OPENROUTER_PRIMARY_MODEL]
        for m in cls.OPENROUTER_FALLBACK_MODELS:
            if m not in models:
                models.append(m)
        return models

    @classmethod
    def is_free_model(cls, model_id: str) -> bool:
        """Check whether a model identifier represents a free model."""
        return model_id.endswith(":free")

    @classmethod
    def validate(cls) -> list[str]:
        """Validate required configuration. Returns list of warnings."""
        warnings = []
        if not cls.OPENROUTER_API_KEY or cls.OPENROUTER_API_KEY == "your_openrouter_api_key":
            warnings.append(
                "OPENROUTER_API_KEY is not configured. "
                "AI extraction will fall back to local OCR until a valid key is set."
            )
        if not cls.OPENROUTER_PRIMARY_MODEL:
            warnings.append("OPENROUTER_PRIMARY_MODEL is not configured.")

        # Check paid model restriction
        if not cls.ALLOW_PAID_MODELS:
            for model_id in cls.get_all_configured_models():
                if not cls.is_free_model(model_id):
                    warnings.append(
                        f"Configured model '{model_id}' is not marked as free, but "
                        "ALLOW_PAID_MODELS is false."
                    )
        return warnings

    @classmethod
    def ensure_directories(cls) -> None:
        """Create necessary directories if they don't exist."""
        cls.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        cls.EASYOCR_MODEL_DIR.mkdir(parents=True, exist_ok=True)


settings = Settings()
