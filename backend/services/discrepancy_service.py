"""
Discrepancy service module.

Performs programmatic cross-validation between EasyOCR text and Vision LLM structured outputs.
Detects significant monetary discrepancies on critical fields (total, subtotal, tax, tip, line items)
and flags them for human review without overriding values or requiring extra AI calls.
"""

from decimal import Decimal, InvalidOperation
import re
from typing import Optional

from backend.schemas.receipt_schema import ReceiptExtraction
from backend.utils.logger import get_logger

logger = get_logger(__name__)

# Monetary tolerance for discrepancy detection ($0.05 allows for minimal 1-cent rounding while catching real errors)
DISCREPANCY_TOLERANCE = Decimal("0.05")

MONEY_REGEX = re.compile(
    r"[\$€£]?\s*([0-9]{1,3}(?:,[0-9]{3})*\.[0-9]{2}|[0-9]+\.[0-9]{2})\b"
)


def clean_decimal(val: Optional[str]) -> Optional[Decimal]:
    """Parse a string to Decimal, removing currency signs, commas, and whitespace."""
    if not val:
        return None
    cleaned = (
        str(val)
        .replace("$", "")
        .replace("€", "")
        .replace("£", "")
        .replace(",", "")
        .strip()
    )
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def extract_confident_ocr_amounts(ocr_text: str) -> dict[str, Decimal]:
    """
    Extract clearly and confidently identifiable monetary fields from OCR text.
    Returns a dictionary of field_name -> Decimal amount.
    Only includes fields where the OCR keyword and amount are unambiguous.
    """
    if not ocr_text or not ocr_text.strip():
        return {}

    lines = [line.strip() for line in ocr_text.splitlines() if line.strip()]
    results: dict[str, Decimal] = {}

    for line in lines:
        lower = line.lower()
        amounts = [clean_decimal(m) for m in MONEY_REGEX.findall(line)]
        amounts = [a for a in amounts if a is not None]

        if not amounts:
            continue

        # 1. Subtotal check (must not be tax/tip)
        if any(k in lower for k in ["subtotal", "sub-total", "sub total"]) and not any(
            k in lower for k in ["tax", "tip", "total due"]
        ):
            results["subtotal"] = amounts[-1]
            continue

        # 2. Tax check (must not be subtotal/total)
        if any(k in lower for k in ["tax", "sales tax", "vat", "gst"]) and not any(
            k in lower for k in ["subtotal", "total"]
        ):
            results["tax"] = amounts[-1]
            continue

        # 3. Tip / Gratuity check
        if any(k in lower for k in ["tip", "gratuity"]) and "total" not in lower:
            results["tip"] = amounts[-1]
            continue

        # 4. Total check (must not be subtotal)
        # Match lines like "TOTAL DUE $43.39", "TOTAL: 99.48", "GRAND TOTAL $50.00", "BALANCE DUE $12.00"
        if any(
            k in lower
            for k in ["total due", "grand total", "balance due", "amount due", "total:"]
        ) or (
            re.search(r"\btotal\b", lower)
            and not any(
                k in lower
                for k in ["subtotal", "sub-total", "sub total", "tax"]
            )
        ):
            results["total_amount"] = amounts[-1]
            continue

    return results


def detect_discrepancies(
    ocr_text: Optional[str],
    extraction: ReceiptExtraction,
    tolerance: Decimal = DISCREPANCY_TOLERANCE,
) -> list[str]:
    """
    Compare confidently identifiable monetary fields from OCR text against LLM extraction.

    Args:
        ocr_text: Raw text from EasyOCR.
        extraction: Structured extraction from Vision LLM.
        tolerance: Maximum acceptable variance before flagging a discrepancy.

    Returns:
        List of warning strings detailing detected discrepancies.
    """
    if not ocr_text or not ocr_text.strip():
        return []

    ocr_amounts = extract_confident_ocr_amounts(ocr_text)
    warnings: list[str] = []

    critical_fields = [
        ("total_amount", "total amount"),
        ("subtotal", "subtotal"),
        ("tax", "tax"),
        ("tip", "tip"),
    ]

    for field_name, display_name in critical_fields:
        if field_name in ocr_amounts:
            ocr_val = ocr_amounts[field_name]
            llm_raw = getattr(extraction, field_name, None)
            llm_val = clean_decimal(llm_raw)

            if llm_val is not None:
                diff = abs(ocr_val - llm_val)
                if diff > tolerance:
                    warnings.append(
                        f"OCR discrepancy detected in {display_name}: OCR text indicates '{ocr_val}', "
                        f"but AI extracted '{llm_val}' (difference: {diff}). Manual review required."
                    )
            elif ocr_val > Decimal("0.00"):
                warnings.append(
                    f"OCR discrepancy detected in {display_name}: OCR text indicates '{ocr_val}', "
                    f"but AI extraction omitted this field. Manual review required."
                )

    # Line items check: where OCR line has a match for an item name and a distinct price
    if extraction.line_items:
        lines = [line.strip() for line in ocr_text.splitlines() if line.strip()]
        for item in extraction.line_items:
            if not item.item_name or not item.price:
                continue
            item_price = clean_decimal(item.price)
            if item_price is None:
                continue

            for line in lines:
                lower_line = line.lower()
                clean_item_name = item.item_name.lower().strip()
                if len(clean_item_name) >= 4 and clean_item_name in lower_line:
                    line_amounts = [clean_decimal(m) for m in MONEY_REGEX.findall(line)]
                    line_amounts = [a for a in line_amounts if a is not None]
                    if len(line_amounts) == 1:
                        ocr_item_price = line_amounts[0]
                        diff = abs(ocr_item_price - item_price)
                        if diff > tolerance:
                            warnings.append(
                                f"OCR discrepancy detected in line item '{item.item_name}': OCR indicates "
                                f"'{ocr_item_price}', but AI extracted '{item.price}'. Manual review required."
                            )
                    break

    if warnings:
        logger.warning(
            f"Detected {len(warnings)} discrepancy warning(s) between OCR and LLM extraction."
        )

    return warnings
