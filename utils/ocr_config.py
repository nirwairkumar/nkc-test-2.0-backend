"""
OCR Configuration for Enhanced PDF Extractor
Automatically detects and configures Tesseract OCR
"""
import os
import sys
import subprocess
from pathlib import Path

def find_tesseract():
    """
    Automatically find Tesseract installation
    """
    # Common installation paths
    common_paths = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        r"/usr/bin/tesseract",
        r"/usr/local/bin/tesseract",
        r"/opt/homebrew/bin/tesseract",  # macOS with Homebrew
    ]
    
    # Check if tesseract is in PATH
    try:
        result = subprocess.run(
            ["tesseract", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            print("✅ Tesseract found in PATH")
            return "tesseract"  # Use system PATH
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    
    # Check common installation paths
    for path in common_paths:
        if Path(path).exists():
            print(f"✅ Tesseract found at: {path}")
            return path
    
    return None


def configure_tesseract():
    """
    Configure pytesseract with correct path
    """
    tesseract_path = find_tesseract()
    
    if tesseract_path:
        try:
            import pytesseract
            if tesseract_path != "tesseract":
                pytesseract.pytesseract.tesseract_cmd = tesseract_path
            print("✅ Tesseract OCR configured successfully")
            return True
        except ImportError:
            print("⚠️  pytesseract not installed. OCR will be disabled.")
            print("   Install with: pip install pytesseract")
            return False
    else:
        print("❌ Tesseract OCR not found!")
        print("\n📥 Installation Instructions:")
        print("\nWindows:")
        print("  1. Download from: https://github.com/UB-Mannheim/tesseract/wiki")
        print("  2. Install to default location")
        print("  3. Restart your terminal/IDE")
        print("\nLinux:")
        print("  sudo apt-get install tesseract-ocr")
        print("\nmacOS:")
        print("  brew install tesseract")
        print("\n⚠️  OCR features will be disabled until Tesseract is installed.")
        return False


# Auto-configure on import
if __name__ == "__main__":
    configure_tesseract()
else:
    # Silent configuration on import
    try:
        tesseract_path = find_tesseract()
        if tesseract_path and tesseract_path != "tesseract":
            import pytesseract
            pytesseract.pytesseract.tesseract_cmd = tesseract_path
    except:
        pass  # Fail silently, OCR will be disabled
