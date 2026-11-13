"""
Receipt history component for the Streamlit frontend.

Displays the list of previously processed receipts.
"""

import streamlit as st
import pandas as pd

from frontend.api_client import get_receipts, get_receipt_detail


def render_receipt_history() -> None:
    """
    Render the receipt history section with a table and detail view.
    """
    st.subheader("📚 Receipt History")

    try:
        receipts = get_receipts()
    except Exception as e:
        st.error(f"Failed to load receipt history: {e}")
        return

    if not receipts:
        st.info("No receipts processed yet. Upload a receipt to get started!")
        return

    # Build history table
    history_data = []
    for r in receipts:
        history_data.append({
            "ID": r["id"],
            "Filename": r["filename"],
            "Merchant": r.get("merchant_name", "N/A"),
            "Date": r.get("date", "N/A"),
            "Total": f"${r['total_amount']:.2f}" if r.get("total_amount") is not None else "N/A",
            "Status": r.get("status", "UNKNOWN"),
            "Created": r.get("created_at", "N/A"),
        })

    df = pd.DataFrame(history_data)
    st.dataframe(df, use_container_width=True, hide_index=True)

    # Detail view selector
    receipt_ids = [r["id"] for r in receipts]
    if receipt_ids:
        st.markdown("---")
        selected_id = st.selectbox(
            "Select a receipt to view details:",
            options=receipt_ids,
            format_func=lambda x: f"Receipt #{x} - {next((r.get('merchant_name', r['filename']) for r in receipts if r['id'] == x), 'Unknown')}",
        )

        if selected_id and st.button("📖 View Full Details"):
            try:
                detail = get_receipt_detail(selected_id)
                st.session_state["selected_receipt"] = detail
            except Exception as e:
                st.error(f"Failed to load receipt details: {e}")

    # Show selected receipt details
    if "selected_receipt" in st.session_state and st.session_state["selected_receipt"]:
        from frontend.components.receipt_display import render_receipt_display
        st.markdown("---")
        render_receipt_display(st.session_state["selected_receipt"])

