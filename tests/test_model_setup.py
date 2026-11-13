"""
Unit tests for EasyOCR model setup and caching.
Verifies weight checking, local reuse, and download safety.
"""

from pathlib import Path
from unittest.mock import patch, MagicMock
import tempfile
import pytest

from setup_models import check_models_exist, reuse_existing_weights, setup


class TestModelSetupAndCaching:
    """Tests for setup_models script functions."""

    def test_check_models_exist_when_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            status = check_models_exist(tmp_path)
            assert status["craft_mlt_25k.pth"] is False
            assert status["english_g2.pth"] is False

    def test_check_models_exist_when_populated(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            (tmp_path / "craft_mlt_25k.pth").write_bytes(b"dummy_weights")
            (tmp_path / "english_g2.pth").write_bytes(b"dummy_weights")

            status = check_models_exist(tmp_path)
            assert status["craft_mlt_25k.pth"] is True
            assert status["english_g2.pth"] is True

    def test_reuse_existing_weights(self):
        with tempfile.TemporaryDirectory() as src_dir, tempfile.TemporaryDirectory() as dest_dir:
            src_path = Path(src_dir)
            dest_path = Path(dest_dir)

            (src_path / "craft_mlt_25k.pth").write_bytes(b"craft_model_data")
            (src_path / "english_g2.pth").write_bytes(b"english_model_data")

            copied = reuse_existing_weights(src_path, dest_path)
            assert len(copied) == 2
            assert (dest_path / "craft_mlt_25k.pth").exists()
            assert (dest_path / "english_g2.pth").exists()

            # Second call should not recopy existing
            second_copied = reuse_existing_weights(src_path, dest_path)
            assert len(second_copied) == 0

    @patch("setup_models.check_models_exist")
    def test_setup_success_when_all_models_present(self, mock_check):
        mock_check.return_value = {
            "craft_mlt_25k.pth": True,
            "english_g2.pth": True,
        }
        ret = setup()
        assert ret == 0
