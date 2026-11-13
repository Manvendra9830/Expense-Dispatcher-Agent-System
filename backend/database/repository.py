"""
Database repository module.

Data access layer for receipt CRUD operations.
"""

import json
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from backend.database.models import Receipt, ReceiptItem
from backend.schemas.receipt_schema import ReceiptExtraction, LineItem
from backend.utils.logger import get_logger
from backend.utils.exceptions import DatabaseError, ReceiptNotFoundError

logger = get_logger(__name__)


def create_receipt(
    db: Session,
    filename: str,
    file_path: str,
    extraction: ReceiptExtraction,
    raw_ocr_text: str,
    status: str = "COMPLETED",
) -> Receipt:
    """
    Create a new receipt record with its line items.

    Args:
        db: Database session.
        filename: Original uploaded filename.
        file_path: Server-side file path.
        extraction: Validated extraction data.
        raw_ocr_text: Raw OCR text output.
        status: Processing status.

    Returns:
        Created Receipt instance.

    Raises:
        DatabaseError: If insertion fails.
    """
    try:
        # Parse date
        receipt_date: date | None = None
        if extraction.date:
            try:
                receipt_date = date.fromisoformat(extraction.date)
            except ValueError:
                receipt_date = None

        # Build receipt record
        receipt = Receipt(
            filename=filename,
            file_path=file_path,
            merchant_name=extraction.merchant_name,
            date=receipt_date,
            subtotal=Decimal(extraction.subtotal) if extraction.subtotal else None,
            tax=Decimal(extraction.tax) if extraction.tax else None,
            tip=Decimal(extraction.tip) if extraction.tip else None,
            total_amount=Decimal(extraction.total_amount) if extraction.total_amount else None,
            extracted_json=extraction.model_dump_json(),
            raw_ocr_text=raw_ocr_text,
            status=status,
        )

        # Add line items
        if extraction.line_items:
            for item in extraction.line_items:
                receipt_item = ReceiptItem(
                    item_name=item.item_name,
                    price=Decimal(item.price) if item.price else None,
                )
                receipt.line_items.append(receipt_item)

        db.add(receipt)
        db.commit()
        db.refresh(receipt)
        logger.info(f"Receipt created with ID {receipt.id}")
        return receipt

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create receipt: {e}")
        raise DatabaseError(f"Failed to save receipt: {str(e)}")


def create_failed_receipt(
    db: Session,
    filename: str,
    file_path: str,
    raw_ocr_text: str | None = None,
    status: str = "FAILED",
    extracted_json: str | None = None,
) -> Receipt:
    """
    Create a receipt record for a failed or review-required extraction.

    Args:
        db: Database session.
        filename: Original uploaded filename.
        file_path: Server-side file path.
        raw_ocr_text: Raw OCR text if available.
        status: Processing status (FAILED or REVIEW_REQUIRED).
        extracted_json: Partial extraction JSON if available.

    Returns:
        Created Receipt instance.
    """
    try:
        receipt = Receipt(
            filename=filename,
            file_path=file_path,
            raw_ocr_text=raw_ocr_text,
            status=status,
            extracted_json=extracted_json,
        )
        db.add(receipt)
        db.commit()
        db.refresh(receipt)
        logger.info(f"Failed receipt record created with ID {receipt.id}, status={status}")
        return receipt
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create failed receipt record: {e}")
        raise DatabaseError(f"Failed to save receipt record: {str(e)}")


def get_receipt_by_id(db: Session, receipt_id: int) -> Receipt:
    """
    Retrieve a receipt by its ID.

    Args:
        db: Database session.
        receipt_id: Receipt primary key.

    Returns:
        Receipt instance.

    Raises:
        ReceiptNotFoundError: If receipt does not exist.
    """
    receipt = db.query(Receipt).filter(Receipt.id == receipt_id).first()
    if not receipt:
        raise ReceiptNotFoundError(receipt_id)
    return receipt


def get_all_receipts(db: Session, limit: int = 100, offset: int = 0) -> list[Receipt]:
    """
    Retrieve all receipts ordered by creation date descending.

    Args:
        db: Database session.
        limit: Maximum number of records to return.
        offset: Number of records to skip.

    Returns:
        List of Receipt instances.
    """
    return (
        db.query(Receipt)
        .order_by(Receipt.created_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )


def delete_receipt(db: Session, receipt_id: int) -> bool:
    """
    Delete a receipt and its associated line items.

    Args:
        db: Database session.
        receipt_id: Receipt primary key.

    Returns:
        True if deleted successfully.

    Raises:
        ReceiptNotFoundError: If receipt does not exist.
        DatabaseError: If deletion fails.
    """
    try:
        receipt = get_receipt_by_id(db, receipt_id)
        db.delete(receipt)
        db.commit()
        logger.info(f"Receipt {receipt_id} deleted successfully.")
        return True
    except ReceiptNotFoundError:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete receipt {receipt_id}: {e}")
        raise DatabaseError(f"Failed to delete receipt: {str(e)}")


def get_receipt_stats(db: Session) -> dict:
    """
    Get dashboard statistics.

    Args:
        db: Database session.

    Returns:
        Dictionary with total_receipts, total_expenses,
        successful_extractions, and review_required counts.
    """
    from sqlalchemy import func

    total_receipts = db.query(func.count(Receipt.id)).scalar() or 0
    total_expenses = (
        db.query(func.sum(Receipt.total_amount))
        .filter(Receipt.status == "COMPLETED")
        .scalar()
    ) or Decimal("0.00")
    successful = (
        db.query(func.count(Receipt.id))
        .filter(Receipt.status == "COMPLETED")
        .scalar()
    ) or 0
    review_required = (
        db.query(func.count(Receipt.id))
        .filter(Receipt.status == "REVIEW_REQUIRED")
        .scalar()
    ) or 0

    return {
        "total_receipts": total_receipts,
        "total_expenses": float(total_expenses),
        "successful_extractions": successful,
        "review_required": review_required,
    }

