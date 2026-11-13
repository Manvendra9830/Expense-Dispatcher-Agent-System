"""
FastAPI application entry point.

Configures the FastAPI application, includes routes, initializes the database,
and provides health check and startup validation.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from backend.api.receipt_routes import router as receipt_router
from backend.database.connection import init_db
from backend.utils.config import settings
from backend.utils.logger import get_logger
from backend.utils.exceptions import ReceiptExtractorError

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown events."""
    # Startup
    logger.info("Starting Receipt Extractor API...")

    # Validate configuration
    config_warnings = settings.validate()
    for warning in config_warnings:
        logger.warning(f"Config: {warning}")

    # Ensure directories exist
    settings.ensure_directories()

    # Initialize database
    init_db()

    logger.info(
        f"API ready at http://{settings.BACKEND_HOST}:{settings.BACKEND_PORT}"
    )
    yield
    # Shutdown
    logger.info("Shutting down Receipt Extractor API.")


app = FastAPI(
    title="Receipt Extractor API",
    description=(
        "AI-powered receipt extraction system. "
        "Upload receipt images or PDFs to extract structured information "
        "using OCR and Vision LLM."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware for Streamlit frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global exception handler
@app.exception_handler(ReceiptExtractorError)
async def receipt_extractor_error_handler(
    request: Request, exc: ReceiptExtractorError
):
    """Handle application-specific exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message},
    )


# Include routes
app.include_router(receipt_router, tags=["Receipts"])


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "receipt-extractor"}

