"""
Upload component for the Streamlit frontend.

Provides the file upload widget and process receipt button.
"""

import streamlit as st


def render_upload_section() -> tuple:
    """
    Render the receipt upload section.

    Returns:
        Tuple of (uploaded_file, process_clicked) where uploaded_file
        is the Streamlit UploadedFile or None, and process_clicked is bool.
    """
    st.subheader("📤 Upload Receipt")

    uploaded_file = st.file_uploader(
        "Choose a receipt image or PDF",
        type=["png", "jpg", "jpeg", "pdf"],
        help="Supported formats: PNG, JPG, JPEG, PDF (max 10 MB, max 5 PDF pages)",
    )

    if uploaded_file is not None:
        # Show file info
        file_size_mb = uploaded_file.size / (1024 * 1024)
        st.caption(
            f"📎 **{uploaded_file.name}** "
            f"({file_size_mb:.2f} MB, {uploaded_file.type})"
        )

        # Show image preview for image files
        if uploaded_file.type in ("image/png", "image/jpeg"):
            with st.expander("🔍 Preview", expanded=False):
                st.image(uploaded_file, caption="Receipt Preview", width=400)

    process_clicked = st.button(
        "🚀 Process Receipt",
        disabled=uploaded_file is None,
        type="primary",
        use_container_width=True,
    )

    return uploaded_file, process_clicked

