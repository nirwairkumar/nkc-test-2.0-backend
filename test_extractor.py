"""
Test Script for Enhanced PDF Extractor
Tests all extraction methods and validates output
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ai_preview_importer.pdf_extractor_enhanced import extract_text_blocks_enhanced
from ai_preview_importer.image_extractor_enhanced import extract_images_enhanced
from utils.logger import get_logger

logger = get_logger(__name__)

def test_pdf_extraction(pdf_path):
    """
    Test PDF extraction with a sample file
    """
    print("=" * 80)
    print("🧪 TESTING ENHANCED PDF EXTRACTOR")
    print("=" * 80)
    
    # Read PDF
    try:
        with open(pdf_path, 'rb') as f:
            pdf_bytes = f.read()
        print(f"✅ Loaded PDF: {pdf_path}")
        print(f"   File size: {len(pdf_bytes)} bytes")
    except FileNotFoundError:
        print(f"❌ PDF not found: {pdf_path}")
        return False
    
    # Test text extraction
    print("\n📝 Testing Text Extraction...")
    try:
        text_lines = extract_text_blocks_enhanced(pdf_bytes)
        print(f"✅ Extracted {len(text_lines)} text lines")
        
        if text_lines:
            print("\n   Sample lines:")
            for i, line in enumerate(text_lines[:5]):
                print(f"   [{i+1}] Page {line['page_num']}: {line['text'][:60]}...")
                print(f"       Source: {line.get('source', 'unknown')}")
        else:
            print("⚠️  No text extracted!")
    except Exception as e:
        print(f"❌ Text extraction failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Test image extraction
    print("\n🖼️  Testing Image Extraction...")
    try:
        images = extract_images_enhanced(pdf_bytes)
        print(f"✅ Extracted {len(images)} images")
        
        if images:
            print("\n   Image details:")
            for i, img in enumerate(images[:3]):
                print(f"   [{i+1}] Page {img['page_num']}: {img['width']}x{img['height']} ({img.get('format', 'unknown')})")
                print(f"       Source: {img.get('source', 'unknown')}")
                print(f"       Bbox: {img['bbox']}")
        else:
            print("ℹ️  No images found (this is OK if PDF has no images)")
    except Exception as e:
        print(f"❌ Image extraction failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Summary
    print("\n" + "=" * 80)
    print("📊 EXTRACTION SUMMARY")
    print("=" * 80)
    print(f"Total text lines: {len(text_lines)}")
    print(f"Total images: {len(images)}")
    
    # Check extraction methods used
    sources = set(line.get('source', 'unknown') for line in text_lines)
    print(f"Extraction methods used: {', '.join(sources)}")
    
    if 'ocr' in sources:
        print("⚠️  OCR was used - this PDF might be scanned")
    
    print("\n✅ All tests passed!")
    return True


if __name__ == "__main__":
    # Test with a sample PDF
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
    else:
        # Use test PDF if available
        pdf_path = "test_doc.pdf"
        if not os.path.exists(pdf_path):
            print("Usage: python test_extractor.py <path_to_pdf>")
            print("\nOr create a test_doc.pdf in the current directory")
            sys.exit(1)
    
    success = test_pdf_extraction(pdf_path)
    sys.exit(0 if success else 1)
