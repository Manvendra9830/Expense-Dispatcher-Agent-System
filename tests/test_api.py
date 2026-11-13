"""
Tests for the FastAPI receipt endpoints.

Uses TestClient to test API routes with mocked services.
"""

import io
import json
import pytest
from unittest.mock import patch, MagicMock
from PIL import Image

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.main import app
from backend.database.connection import Base, get_db


# Create test database
TEST_DATABASE_URL = "sqlite:///./test_receipts.db"
test_engine = create_engine(
    TEST_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=test_engine
)


def override_get_db():
    """Override database dependency for testing."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def setup_test_db():
    """Create and drop test database tables for each test."""
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def sample_image_bytes():
    """Create a minimal valid PNG image for testing."""
    img = Image.new("RGB", (100, 100), color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.read()


@pytest.fixture
def sample_extraction():
    """Sample extraction result dict."""
    return {
        "merchant_name": "Test Store",
        "date": "2026-01-15",
        "line_items": [
            {"item_name": "Item A", "price": "10.99"},
            {"item_name": "Item B", "price": "5.00"},
        ],
        "subtotal": "15.99",
        "tax": "1.28",
        "tip": None,
        "total_amount": "17.27",
        "warnings": [],
    }


class TestHealthEndpoint:
    """Tests for the health check endpoint."""

    def test_health_check(self, client):
        """Health endpoint should return healthy status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


class TestUploadEndpoint:
    """Tests for the POST /upload endpoint."""

    @patch("backend.services.extraction_service.extract_receipt_data")
    @patch("backend.services.ocr_service._get_reader")
    def test_upload_valid_image(
        self, mock_ocr_reader, mock_llm, client, sample_image_bytes, sample_extraction
    ):
        """Uploading a valid image should process and return extraction."""
        # Mock OCR reader
        mock_reader = MagicMock()
        mock_reader.readtext.return_value = ["Test Store", "$17.27"]
        mock_ocr_reader.return_value = mock_reader

        # Mock LLM response
        mock_llm.return_value = json.dumps(sample_extraction)

        response = client.post(
            "/upload",
            files={"file": ("test_receipt.png", sample_image_bytes, "image/png")},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["merchant_name"] == "Test Store"
        assert data["status"] in ("COMPLETED", "REVIEW_REQUIRED")
        assert data["id"] is not None

    def test_upload_invalid_file_type(self, client):
        """Uploading an unsupported file type should return 400."""
        response = client.post(
            "/upload",
            files={"file": ("test.txt", b"hello world", "text/plain")},
        )
        assert response.status_code == 400

    def test_upload_empty_file(self, client):
        """Uploading an empty file should return 400."""
        response = client.post(
            "/upload",
            files={"file": ("empty.png", b"", "image/png")},
        )
        assert response.status_code == 400

    def test_upload_corrupted_image(self, client):
        """Uploading a corrupted image should return 400."""
        response = client.post(
            "/upload",
            files={"file": ("bad.png", b"not an image", "image/png")},
        )
        assert response.status_code == 400


class TestReceiptsEndpoint:
    """Tests for the GET /receipts endpoint."""

    def test_list_receipts_empty(self, client):
        """Getting receipts when none exist should return empty list."""
        response = client.get("/receipts")
        assert response.status_code == 200
        assert response.json() == []


class TestStatsEndpoint:
    """Tests for the GET /stats endpoint."""

    def test_stats_empty(self, client):
        """Stats with no receipts should return zeros."""
        response = client.get("/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["total_receipts"] == 0
        assert data["total_expenses"] == 0.0


class TestReceiptDetailEndpoint:
    """Tests for the GET /receipts/{id} endpoint."""

    def test_get_nonexistent_receipt(self, client):
        """Getting a non-existent receipt should return 404."""
        response = client.get("/receipts/99999")
        assert response.status_code == 404


class TestDeleteEndpoint:
    """Tests for the DELETE /receipts/{id} endpoint."""

    def test_delete_nonexistent_receipt(self, client):
        """Deleting a non-existent receipt should return 404."""
        response = client.delete("/receipts/99999")
        assert response.status_code == 404

