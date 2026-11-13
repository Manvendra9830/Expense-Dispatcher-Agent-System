"""
Run script for the Receipt Extractor application.

Starts both the FastAPI backend and Streamlit frontend as separate processes.
"""

import subprocess
import sys
import time
import os


def main():
    """Start the backend and frontend servers."""
    # Determine the Python executable from the current environment
    python_exe = sys.executable
    project_dir = os.path.dirname(os.path.abspath(__file__))

    print("=" * 60)
    print("  Receipt Extractor - Starting Application")
    print("=" * 60)
    print(f"  Python: {python_exe}")
    print(f"  Project: {project_dir}")
    print()

    # Start FastAPI backend
    print("🚀 Starting FastAPI backend on http://127.0.0.1:8000 ...")
    backend_process = subprocess.Popen(
        [
            python_exe, "-m", "uvicorn",
            "backend.main:app",
            "--host", "127.0.0.1",
            "--port", "8000",
            "--reload",
        ],
        cwd=project_dir,
    )

    # Wait for backend to start
    time.sleep(3)

    # Start Streamlit frontend
    print("🎨 Starting Streamlit frontend on http://127.0.0.1:8501 ...")
    frontend_process = subprocess.Popen(
        [
            python_exe, "-m", "streamlit", "run",
            "frontend/app.py",
            "--server.port", "8501",
            "--server.address", "127.0.0.1",
        ],
        cwd=project_dir,
    )

    print()
    print("=" * 60)
    print("  Application is running!")
    print("  Backend:  http://127.0.0.1:8000")
    print("  Swagger:  http://127.0.0.1:8000/docs")
    print("  Frontend: http://127.0.0.1:8501")
    print("  Press Ctrl+C to stop both servers.")
    print("=" * 60)

    try:
        backend_process.wait()
    except KeyboardInterrupt:
        print("\n🛑 Shutting down...")
        backend_process.terminate()
        frontend_process.terminate()
        backend_process.wait()
        frontend_process.wait()
        print("✅ Both servers stopped.")


if __name__ == "__main__":
    main()

