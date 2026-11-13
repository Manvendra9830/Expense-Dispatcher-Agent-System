"""
Streamlit frontend application.

Main dashboard for the Receipt Extractor system.
Provides upload, extraction display, and history views.
"""

import streamlit as st

from frontend.api_client import (
    upload_receipt,
    get_dashboard_stats,
    check_backend_health,
)
from frontend.components.upload import render_upload_section
from frontend.components.receipt_display import render_receipt_display
from frontend.components.receipt_history import render_receipt_history


# Page configuration
st.set_page_config(
    page_title="Receipt Extractor",
    page_icon="🧾",
    layout="wide",
    initial_sidebar_state="expanded",
)


def render_dashboard():
    """Render the dashboard statistics section."""
    st.subheader("📊 Dashboard")

    try:
        stats = get_dashboard_stats()
    except Exception:
        stats = {
            "total_receipts": 0,
            "total_expenses": 0.0,
            "successful_extractions": 0,
            "review_required": 0,
        }

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("📄 Total Receipts", stats["total_receipts"])
    with col2:
        st.metric("💰 Total Expenses", f"${stats['total_expenses']:.2f}")
    with col3:
        st.metric("✅ Successful", stats["successful_extractions"])
    with col4:
        st.metric("⚠️ Needs Review", stats["review_required"])


def main():
    """Main application entry point."""
    # Header
    st.title("🧾 Receipt Extractor")
    st.caption("AI-powered receipt data extraction using OCR and Vision LLM")

    # Check backend health
    backend_healthy = check_backend_health()
    if not backend_healthy:
        st.error(
            "⚠️ Backend is not reachable. "
            "Please start the FastAPI server: "
            "`uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000`"
        )

    # Sidebar navigation
    st.sidebar.title("Navigation")
    page = st.sidebar.radio(
        "Go to:",
        ["🏠 Dashboard", "📤 Upload Receipt", "📚 Receipt History"],
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown(
        "**Receipt Extractor v1.0**\n\n"
        "Part 1: Receipt Extraction System\n\n"
        "Built with FastAPI, Streamlit, EasyOCR & OpenRouter"
    )

    # Backend status indicator in sidebar
    if backend_healthy:
        st.sidebar.success("🟢 Backend Connected")
    else:
        st.sidebar.error("🔴 Backend Offline")

    # Page routing
    if page == "🏠 Dashboard":
        render_dashboard()
        st.markdown("---")
        render_receipt_history()

    elif page == "📤 Upload Receipt":
        uploaded_file, process_clicked = render_upload_section()

        if process_clicked and uploaded_file is not None:
            if not backend_healthy:
                st.error("Cannot process: backend is offline.")
                return

            with st.spinner("🔄 Processing receipt... This may take a moment."):
                try:
                    file_bytes = uploaded_file.getvalue()
                    result = upload_receipt(file_bytes, uploaded_file.name)

                    st.success("✅ Receipt processed successfully!")

                    # Store result in session state
                    st.session_state["last_result"] = result

                except Exception as e:
                    st.error(f"❌ Processing failed: {str(e)}")

        # Display last result
        if "last_result" in st.session_state and st.session_state["last_result"]:
            st.markdown("---")
            render_receipt_display(st.session_state["last_result"])

    elif page == "📚 Receipt History":
        render_receipt_history()


if __name__ == "__main__":
    main()

