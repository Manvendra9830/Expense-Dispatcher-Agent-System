"""
Tests for database operations.

Uses a temporary SQLite database for isolation.
"""

import pytest
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database.connection import Base
from backend.database.models import Receipt, ReceiptItem
from backend.database.repository import (
    create_receipt,
    create_failed_receipt,
    get_receipt_by_id,
    get_all_receipts,
    delete_receipt,
    get_receipt_stats,
)
from backend.schemas.receipt_schema import ReceiptExtraction, LineItem
from backend.utils.exceptions import ReceiptNotFoundError


# Test database setup
TEST_DB_URL = "sqlite:///./test_db_operations.db"
test_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(autouse=True)
def setup_db():
    """Create and drop tables for each test."""
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db():
    """Get a test database session."""
    session = TestSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def sample_extraction():
    """Create a sample ReceiptExtraction for testing."""
    return ReceiptExtraction(
        merchant_name="Test Mart",
        date="2026-03-15",
        line_items=[
            LineItem(item_name="Widget A", price="12.99"),
            LineItem(item_name="Widget B", price="7.50"),
        ],
        subtotal="20.49",
        tax="1.64",
        tip=None,
        total_amount="22.13",
        warnings=[],
    )


class TestCreateReceipt:
    """Tests for creating receipt records."""

    def test_create_receipt_success(self, db, sample_extraction):
        """Creating a receipt should persist all fields and line items."""
        receipt = create_receipt(
            db=db,
            filename="receipt_001.png",
            file_path="/uploads/receipt_001.png",
            extraction=sample_extraction,
            raw_ocr_text="Test OCR output text",
            status="COMPLETED",
        )

        assert receipt.id is not None
        assert receipt.filename == "receipt_001.png"
        assert receipt.merchant_name == "Test Mart"
        assert receipt.total_amount == Decimal("22.13")
        assert receipt.status == "COMPLETED"
        assert len(receipt.line_items) == 2
        assert receipt.line_items[0].item_name == "Widget A"
        assert receipt.line_items[0].price == Decimal("12.99")

    def test_create_receipt_nullable_fields(self, db):
        """Receipt with all nullable fields should be created."""
        extraction = ReceiptExtraction(
            merchant_name=None,
            date=None,
            line_items=[],
            subtotal=None,
            tax=None,
            tip=None,
            total_amount=None,
        )
        receipt = create_receipt(
            db=db,
            filename="unknown.png",
            file_path="/uploads/unknown.png",
            extraction=extraction,
            raw_ocr_text="",
        )
        assert receipt.id is not None
        assert receipt.merchant_name is None
        assert receipt.total_amount is None


class TestCreateFailedReceipt:
    """Tests for creating failed receipt records."""

    def test_create_failed_receipt(self, db):
        """Failed receipt should be stored with correct status."""
        receipt = create_failed_receipt(
            db=db,
            filename="bad_receipt.pdf",
            file_path="/uploads/bad_receipt.pdf",
            raw_ocr_text="Some OCR text",
            status="FAILED",
        )
        assert receipt.id is not None
        assert receipt.status == "FAILED"
        assert receipt.merchant_name is None

    def test_create_review_required_receipt(self, db):
        """Review-required receipt should have correct status."""
        receipt = create_failed_receipt(
            db=db,
            filename="partial.png",
            file_path="/uploads/partial.png",
            status="REVIEW_REQUIRED",
            extracted_json='{"merchant_name": "Partial"}',
        )
        assert receipt.status == "REVIEW_REQUIRED"
        assert receipt.extracted_json is not None


class TestGetReceipt:
    """Tests for retrieving receipt records."""

    def test_get_existing_receipt(self, db, sample_extraction):
        """Getting an existing receipt should return correct data."""
        created = create_receipt(
            db=db,
            filename="test.png",
            file_path="/uploads/test.png",
            extraction=sample_extraction,
            raw_ocr_text="OCR text",
        )
        found = get_receipt_by_id(db, created.id)
        assert found.id == created.id
        assert found.merchant_name == "Test Mart"

    def test_get_nonexistent_receipt_raises(self, db):
        """Getting a non-existent receipt should raise ReceiptNotFoundError."""
        with pytest.raises(ReceiptNotFoundError):
            get_receipt_by_id(db, 99999)


class TestGetAllReceipts:
    """Tests for listing receipts."""

    def test_list_empty(self, db):
        """Listing receipts with none in DB should return empty list."""
        results = get_all_receipts(db)
        assert results == []

    def test_list_multiple(self, db, sample_extraction):
        """Listing receipts should return all created receipts."""
        create_receipt(db, "a.png", "/a.png", sample_extraction, "ocr1")
        create_receipt(db, "b.png", "/b.png", sample_extraction, "ocr2")
        results = get_all_receipts(db)
        assert len(results) == 2


class TestDeleteReceipt:
    """Tests for deleting receipts."""

    def test_delete_existing(self, db, sample_extraction):
        """Deleting an existing receipt should remove it and its items."""
        receipt = create_receipt(db, "del.png", "/del.png", sample_extraction, "ocr")
        rid = receipt.id
        delete_receipt(db, rid)

        with pytest.raises(ReceiptNotFoundError):
            get_receipt_by_id(db, rid)

    def test_delete_nonexistent_raises(self, db):
        """Deleting a non-existent receipt should raise ReceiptNotFoundError."""
        with pytest.raises(ReceiptNotFoundError):
            delete_receipt(db, 99999)


class TestReceiptStats:
    """Tests for dashboard statistics."""

    def test_stats_empty(self, db):
        """Stats with no receipts should return zeros."""
        stats = get_receipt_stats(db)
        assert stats["total_receipts"] == 0
        assert stats["total_expenses"] == 0.0
        assert stats["successful_extractions"] == 0
        assert stats["review_required"] == 0

    def test_stats_with_data(self, db, sample_extraction):
        """Stats should reflect created receipts correctly."""
        create_receipt(db, "a.png", "/a.png", sample_extraction, "ocr", "COMPLETED")
        create_receipt(db, "b.png", "/b.png", sample_extraction, "ocr", "COMPLETED")
        create_failed_receipt(db, "c.png", "/c.png", status="REVIEW_REQUIRED")

        stats = get_receipt_stats(db)
        assert stats["total_receipts"] == 3
        assert stats["successful_extractions"] == 2
        assert stats["review_required"] == 1
        assert stats["total_expenses"] == pytest.approx(44.26, rel=1e-2)

