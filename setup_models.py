#!/usr/bin/env python
"""
Pre-download and cache EasyOCR model weights.

Prepares pretrained detection (CRAFT) and recognition (English) models
in the local 'models/easyocr/' directory so runtime execution never
initiates downloads during receipt uploads.
"""

import sys
import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
TARGET_MODEL_DIR = PROJECT_ROOT / "models" / "easyocr"
DEFAULT_USER_CACHE = Path.home() / ".EasyOCR" / "model"

REQUIRED_MODELS = [
    "craft_mlt_25k.pth",
    "english_g2.pth",
]


def check_models_exist(directory: Path) -> dict[str, bool]:
    """Check existence and non-zero size of required model files."""
    status = {}
    for model_name in REQUIRED_MODELS:
        file_path = directory / model_name
        status[model_name] = file_path.is_file() and file_path.stat().st_size > 0
    return status


def reuse_existing_weights(src_dir: Path, dest_dir: Path) -> list[str]:
    """Copy existing model weights from user cache to local directory."""
    copied = []
    if not src_dir.exists():
        return copied

    dest_dir.mkdir(parents=True, exist_ok=True)
    for model_name in REQUIRED_MODELS:
        src_file = src_dir / model_name
        dest_file = dest_dir / model_name
        if src_file.is_file() and src_file.stat().st_size > 0 and not dest_file.exists():
            size_mb = src_file.stat().st_size / (1024 * 1024)
            print(f"Reusing cached model '{model_name}' ({size_mb:.1f} MB) from {src_dir}...")
            shutil.copy2(src_file, dest_file)
            copied.append(model_name)
    return copied


def download_missing_models(target_dir: Path) -> None:
    """Trigger EasyOCR download for missing weights into target_dir."""
    target_dir.mkdir(parents=True, exist_ok=True)
    print(f"Initializing EasyOCR downloader targeted at: {target_dir}")
    try:
        import easyocr
        # Initializing reader with download_enabled=True populates model_storage_directory
        easyocr.Reader(
            ["en"],
            gpu=False,
            model_storage_directory=str(target_dir),
            download_enabled=True,
            verbose=True,
        )
    except Exception as e:
        print(f"ERROR: Failed to download EasyOCR models: {e}", file=sys.stderr)
        raise


def setup() -> int:
    """Main preparation entry point."""
    print("=" * 60)
    print("EasyOCR Model Preparation & Verification")
    print(f"Target Directory: {TARGET_MODEL_DIR}")
    print("=" * 60)

    TARGET_MODEL_DIR.mkdir(parents=True, exist_ok=True)

    # Step 1: Check existing weights in target directory
    status = check_models_exist(TARGET_MODEL_DIR)
    all_present = all(status.values())

    # Step 2: Try reusing from default ~/.EasyOCR/model if target is missing files
    if not all_present:
        print(f"Checking existing global cache at {DEFAULT_USER_CACHE}...")
        copied = reuse_existing_weights(DEFAULT_USER_CACHE, TARGET_MODEL_DIR)
        if copied:
            print(f"Successfully migrated {len(copied)} model(s) to {TARGET_MODEL_DIR}")
        status = check_models_exist(TARGET_MODEL_DIR)
        all_present = all(status.values())

    # Step 3: Download any still-missing weights
    if not all_present:
        missing = [m for m, present in status.items() if not present]
        print(f"Missing models: {missing}. Downloading now...")
        try:
            download_missing_models(TARGET_MODEL_DIR)
        except Exception as e:
            print(f"Model setup failed: {e}", file=sys.stderr)
            return 1

    # Step 4: Final verification
    final_status = check_models_exist(TARGET_MODEL_DIR)
    print("\nModel Verification:")
    for model_name, present in final_status.items():
        file_path = TARGET_MODEL_DIR / model_name
        if present:
            size_mb = file_path.stat().st_size / (1024 * 1024)
            print(f"  [OK] {model_name} ({size_mb:.2f} MB)")
        else:
            print(f"  [MISSING] {model_name}")

    if all(final_status.values()):
        print("\nSUCCESS: All EasyOCR models are prepared and cached locally.")
        print("Application runtime will load models offline without network downloads.")
        return 0
    else:
        print("\nERROR: Verification failed. Some required models are missing.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(setup())
