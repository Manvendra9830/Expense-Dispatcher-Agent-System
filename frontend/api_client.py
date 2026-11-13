"""
Frontend API client module.

Communicates with the FastAPI backend using HTTPX.
"""

from typing import Optional
import httpx

# Default backend URL - can be overridden via environment
BACKEND_BASE_URL = "http://127.0.0.1:8000"
TIMEOUT = 120.0  # 2 minutes for receipt processing


def get_backend_url() -> str:
    """Get the backend base URL from environment or default."""
    import os
    return os.getenv("BACKEND_BASE_URL", BACKEND_BASE_URL)


def upload_receipt(file_bytes: bytes, filename: str) -> dict:
    """
    Upload a receipt file to the backend for processing.

    Args:
        file_bytes: File content as bytes.
        filename: Original filename.

    Returns:
        Parsed JSON response dict.

    Raises:
        Exception: If the request fails.
    """
    url = f"{get_backend_url()}/upload"
    files = {"file": (filename, file_bytes)}

    with httpx.Client(timeout=TIMEOUT) as client:
        response = client.post(url, files=files)

    if response.status_code != 200:
        error_detail = response.json().get("detail", "Unknown error")
        raise Exception(f"Upload failed: {error_detail}")

    return response.json()


def get_receipts() -> list[dict]:
    """
    Fetch all receipts from the backend.

    Returns:
        List of receipt dicts.
    """
    url = f"{get_backend_url()}/receipts"

    with httpx.Client(timeout=30.0) as client:
        response = client.get(url)

    if response.status_code != 200:
        raise Exception("Failed to fetch receipts.")

    return response.json()


def get_receipt_detail(receipt_id: int) -> dict:
    """
    Fetch a single receipt with full details.

    Args:
        receipt_id: Receipt ID.

    Returns:
        Receipt detail dict.
    """
    url = f"{get_backend_url()}/receipts/{receipt_id}"

    with httpx.Client(timeout=30.0) as client:
        response = client.get(url)

    if response.status_code != 200:
        raise Exception(f"Failed to fetch receipt {receipt_id}.")

    return response.json()


def delete_receipt(receipt_id: int) -> dict:
    """
    Delete a receipt.

    Args:
        receipt_id: Receipt ID.

    Returns:
        Response dict.
    """
    url = f"{get_backend_url()}/receipts/{receipt_id}"

    with httpx.Client(timeout=30.0) as client:
        response = client.delete(url)

    if response.status_code != 200:
        raise Exception(f"Failed to delete receipt {receipt_id}.")

    return response.json()


def get_dashboard_stats() -> dict:
    """
    Fetch dashboard statistics.

    Returns:
        Stats dict with total_receipts, total_expenses, etc.
    """
    url = f"{get_backend_url()}/stats"

    with httpx.Client(timeout=30.0) as client:
        response = client.get(url)

    if response.status_code != 200:
        return {
            "total_receipts": 0,
            "total_expenses": 0.0,
            "successful_extractions": 0,
            "review_required": 0,
        }

    return response.json()


def check_backend_health() -> bool:
    """
    Check if the backend is reachable.

    Returns:
        True if healthy, False otherwise.
    """
    try:
        url = f"{get_backend_url()}/health"
        with httpx.Client(timeout=5.0) as client:
            response = client.get(url)
        return response.status_code == 200
    except Exception:
        return False

