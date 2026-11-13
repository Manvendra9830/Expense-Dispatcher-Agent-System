"""
FastAPI receipt routes.

REST API endpoints for receipt upload, retrieval, and deletion.
"""

import json
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database.connection import get_db
from backend.database.repository import (
    get_all_receipts,
    get_receipt_by_id,
    delete_receipt,
    get_receipt_stats,
)
from backend.services.extraction_service import process_receipt
from backend.schemas.receipt_schema import (
    ReceiptResponse,
    ReceiptListItem,
    DashboardStats,
    ErrorResponse,
    LineItem,
)
from backend.utils.logger import get_logger
from backend.utils.exceptions import ReceiptExtractorError

logger = get_logger(__name__)

router = APIRouter()


def _receipt_to_response(receipt) -> ReceiptResponse:
    """Convert a Receipt ORM model to a ReceiptResponse schema."""
    # Parse line items from the relationship
    line_items = []
    for item in receipt.line_items:
        line_items.append(LineItem(
            item_name=item.item_name,
            price=str(item.price) if item.price is not None else None,
        ))

    # Parse warnings from extracted_json
    warnings = []
    if receipt.extracted_json:
        try:
            extracted = json.loads(receipt.extracted_json)
            warnings = extracted.get("warnings", [])
        except (json.JSONDecodeError, TypeError):
            pass

    return ReceiptResponse(
        id=receipt.id,
        filename=receipt.filename,
        merchant_name=receipt.merchant_name,
        date=receipt.date.isoformat() if receipt.date else None,
        line_items=line_items,
        subtotal=float(receipt.subtotal) if receipt.subtotal is not None else None,
        tax=float(receipt.tax) if receipt.tax is not None else None,
        tip=float(receipt.tip) if receipt.tip is not None else None,
        total_amount=float(receipt.total_amount) if receipt.total_amount is not None else None,
        status=receipt.status,
        warnings=warnings,
        raw_ocr_text=receipt.raw_ocr_text,
        created_at=receipt.created_at.isoformat() if receipt.created_at else None,
    )


@router.post("/upload", response_model=ReceiptResponse)
async def upload_receipt(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Upload and process a receipt image or PDF.

    Accepts PNG, JPG, JPEG, and PDF files. Processes the file through
    OCR and LLM extraction, validates the result, and stores it.

    Returns the structured extraction result.
    """
    try:
        # Read file content
        content = await file.read()
        filename = file.filename or "unknown"

        logger.info(f"Received upload: {filename} ({len(content)} bytes)")

        # Process through the extraction pipeline
        receipt = process_receipt(
            filename=filename,
            content=content,
            db=db,
        )

        return _receipt_to_response(receipt)

    except ReceiptExtractorError as e:
        logger.error(f"Processing error: {e.message}")
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(f"Unexpected error during upload: {e}")
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while processing the receipt.",
        )


@router.get("/receipts", response_model=list[ReceiptListItem])
async def list_receipts(
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """
    List all processed receipts.

    Returns a simplified list ordered by creation date (newest first).
    """
    try:
        receipts = get_all_receipts(db, limit=limit, offset=offset)
        result = []
        for r in receipts:
            result.append(ReceiptListItem(
                id=r.id,
                filename=r.filename,
                merchant_name=r.merchant_name,
                date=r.date.isoformat() if r.date else None,
                total_amount=float(r.total_amount) if r.total_amount is not None else None,
                status=r.status,
                created_at=r.created_at.isoformat() if r.created_at else None,
            ))
        return result
    except Exception as e:
        logger.error(f"Error listing receipts: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve receipts.")


@router.get("/receipts/{receipt_id}", response_model=ReceiptResponse)
async def get_receipt(
    receipt_id: int,
    db: Session = Depends(get_db),
):
    """
    Get a single receipt with full extracted information and line items.
    """
    try:
        receipt = get_receipt_by_id(db, receipt_id)
        return _receipt_to_response(receipt)
    except ReceiptExtractorError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(f"Error retrieving receipt {receipt_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve receipt.")


@router.delete("/receipts/{receipt_id}")
async def remove_receipt(
    receipt_id: int,
    db: Session = Depends(get_db),
):
    """
    Delete a receipt and its associated line items.
    """
    try:
        delete_receipt(db, receipt_id)
        return {"detail": f"Receipt {receipt_id} deleted successfully."}
    except ReceiptExtractorError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(f"Error deleting receipt {receipt_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete receipt.")


@router.get("/stats", response_model=DashboardStats)
async def dashboard_stats(
    db: Session = Depends(get_db),
):
    """
    Get dashboard statistics: total receipts, expenses, successful extractions,
    and receipts requiring review.
    """
    try:
        stats = get_receipt_stats(db)
        return DashboardStats(**stats)
    except Exception as e:
        logger.error(f"Error fetching stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve statistics.")

