"""
Receipt display component for the Streamlit frontend.

Displays the extracted receipt information.
"""

import streamlit as st
import pandas as pd


def render_receipt_display(receipt: dict) -> None:
    """
    Display the extracted receipt information.

    Args:
        receipt: Receipt data dict from the API.
    """
    if not receipt:
        return

    st.subheader("📋 Extracted Receipt Information")

    # Status badge
    status = receipt.get("status", "UNKNOWN")
    status_colors = {
        "COMPLETED": "🟢",
        "REVIEW_REQUIRED": "🟡",
        "FAILED": "🔴",
        "PROCESSING": "🔵",
    }
    status_icon = status_colors.get(status, "⚪")
    st.markdown(f"**Status:** {status_icon} {status}")

    # Main info in columns
    col1, col2 = st.columns(2)

    with col1:
        st.markdown(f"**🏪 Merchant:** {receipt.get('merchant_name', 'N/A')}")
        st.markdown(f"**📅 Date:** {receipt.get('date', 'N/A')}")
        st.markdown(f"**📄 File:** {receipt.get('filename', 'N/A')}")

    with col2:
        subtotal = receipt.get("subtotal")
        tax = receipt.get("tax")
        tip = receipt.get("tip")
        total = receipt.get("total_amount")

        st.markdown(f"**Subtotal:** ${subtotal:.2f}" if subtotal is not None else "**Subtotal:** N/A")
        st.markdown(f"**Tax:** ${tax:.2f}" if tax is not None else "**Tax:** N/A")
        st.markdown(f"**Tip:** ${tip:.2f}" if tip is not None else "**Tip:** N/A")
        st.markdown(f"**💰 Total:** ${total:.2f}" if total is not None else "**💰 Total:** N/A")

    # Line items table
    line_items = receipt.get("line_items", [])
    if line_items:
        st.markdown("**🛒 Line Items:**")
        items_df = pd.DataFrame(line_items)
        if "item_name" in items_df.columns:
            items_df.columns = ["Item Name", "Price"]
            # Format price column
            items_df["Price"] = items_df["Price"].apply(
                lambda x: f"${float(x):.2f}" if x is not None else "N/A"
            )
        st.dataframe(items_df, use_container_width=True, hide_index=True)
    else:
        st.info("No line items extracted.")

    # Warnings
    warnings = receipt.get("warnings", [])
    if warnings:
        with st.expander(f"⚠️ Validation Warnings ({len(warnings)})", expanded=True):
            for w in warnings:
                st.warning(w)

    # Raw OCR text (collapsible)
    raw_ocr = receipt.get("raw_ocr_text")
    if raw_ocr:
        with st.expander("📝 Raw OCR Text", expanded=False):
            st.text(raw_ocr)

