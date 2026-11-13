"""
Validation service module.

Business logic validation for extracted receipt data.
"""

from decimal import Decimal, InvalidOperation
from typing import Optional

from backend.schemas.receipt_schema import ReceiptExtraction
from backend.utils.logger import get_logger

logger = get_logger(__name__)

# Acceptable rounding tolerance for arithmetic checks
TOLERANCE = Decimal("0.50")


def validate_extraction(extraction: ReceiptExtraction) -> ReceiptExtraction:
    """
    Apply business validation rules to an extraction result.

    Checks:
    - Negative amounts.
    - Subtotal + tax + tip ≈ total consistency.
    - Missing critical fields.
    - Line item sum vs subtotal.

    Args:
        extraction: Pydantic-validated extraction result.

    Returns:
        The extraction with any new warnings appended.
    """
    warnings = list(extraction.warnings)

    # Check for missing critical fields
    if not extraction.merchant_name:
        warnings.append("Merchant name is missing.")
    if not extraction.date:
        warnings.append("Receipt date is missing or could not be parsed.")
    if not extraction.total_amount:
        warnings.append("Total amount is missing.")

    # Check for negative amounts
    for field_name in ("subtotal", "tax", "tip", "total_amount"):
        value = getattr(extraction, field_name)
        if value is not None:
            try:
                dec = Decimal(value)
                if dec < 0:
                    warnings.append(f"{field_name} is negative: {value}")
            except InvalidOperation:
                warnings.append(f"{field_name} is not a valid number: {value}")

    # Check line item prices
    for i, item in enumerate(extraction.line_items):
        if item.price is not None:
            try:
                price = Decimal(item.price)
                if price < 0:
                    warnings.append(
                        f"Line item '{item.item_name}' has negative price: {item.price}"
                    )
            except InvalidOperation:
                warnings.append(
                    f"Line item '{item.item_name}' has invalid price: {item.price}"
                )

    # Check arithmetic consistency: subtotal + tax + tip ≈ total
    if extraction.total_amount and extraction.subtotal:
        try:
            total = Decimal(extraction.total_amount)
            subtotal = Decimal(extraction.subtotal)
            tax = Decimal(extraction.tax) if extraction.tax else Decimal("0")
            tip = Decimal(extraction.tip) if extraction.tip else Decimal("0")

            expected_total = subtotal + tax + tip
            diff = abs(total - expected_total)

            if diff > TOLERANCE:
                warnings.append(
                    f"Arithmetic check: subtotal ({subtotal}) + tax ({tax}) + "
                    f"tip ({tip}) = {expected_total}, but total is {total} "
                    f"(difference: {diff}). This may indicate discounts, fees, "
                    f"or extraction inaccuracy."
                )
        except InvalidOperation:
            pass  # Already flagged in individual field checks

    # Check line items sum vs subtotal
    if extraction.subtotal and extraction.line_items:
        try:
            subtotal = Decimal(extraction.subtotal)
            items_sum = Decimal("0")
            all_valid = True
            for item in extraction.line_items:
                if item.price is not None:
                    try:
                        items_sum += Decimal(item.price)
                    except InvalidOperation:
                        all_valid = False
                        break

            if all_valid and items_sum > 0:
                diff = abs(subtotal - items_sum)
                if diff > TOLERANCE:
                    warnings.append(
                        f"Line items sum ({items_sum}) differs from "
                        f"subtotal ({subtotal}) by {diff}. "
                        f"Possible missing items or extraction error."
                    )
        except InvalidOperation:
            pass

    # Check for empty line items
    if not extraction.line_items:
        warnings.append("No line items were extracted.")

    # Update the extraction with new warnings
    extraction.warnings = warnings

    if warnings:
        logger.info(f"Validation completed with {len(warnings)} warning(s).")
    else:
        logger.info("Validation passed with no warnings.")

    return extraction


def determine_status(extraction: ReceiptExtraction) -> str:
    """
    Determine the processing status based on extraction quality.

    Args:
        extraction: Validated extraction result.

    Returns:
        Status string: COMPLETED or REVIEW_REQUIRED.
    """
    # Count critical issues
    critical_missing = 0
    if not extraction.merchant_name:
        critical_missing += 1
    if not extraction.total_amount:
        critical_missing += 1
    if not extraction.line_items:
        critical_missing += 1

    # More than one critical field missing → needs review
    if critical_missing >= 2:
        return "REVIEW_REQUIRED"

    # Check if there are concerning warnings
    concerning_keywords = ["negative", "invalid", "not a valid"]
    for warning in extraction.warnings:
        for keyword in concerning_keywords:
            if keyword in warning.lower():
                return "REVIEW_REQUIRED"

    return "COMPLETED"

