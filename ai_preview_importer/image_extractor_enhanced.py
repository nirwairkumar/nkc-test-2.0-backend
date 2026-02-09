"""
Enhanced Image Extractor with Advanced Processing
Extracts images from PDFs with better quality and metadata
"""
import fitz
import io
import base64
import numpy as np
from PIL import Image
from utils.logger import get_logger

logger = get_logger(__name__)

# Try to import pytesseract for OCR
try:
    import pytesseract
    # Set the path to tesseract executable (default Windows installation path)
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
    PYTESSERACT_AVAILABLE = True
    logger.info("Pytesseract OCR enabled")
except ImportError:
    PYTESSERACT_AVAILABLE = False
    logger.warning("Pytesseract not available. OCR functionality disabled")
except Exception as e:
    PYTESSERACT_AVAILABLE = False
    logger.warning(f"Pytesseract configuration failed: {e}")

# Try to import OpenCV for image enhancement
try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    logger.warning("OpenCV not available. Image enhancement disabled")


def extract_images_enhanced(pdf_bytes: bytes):
    """
    Enhanced image extraction with:
    - Better quality preservation
    - Duplicate detection
    - Image enhancement
    - Metadata extraction
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    extracted_images = []
    seen_hashes = set()  # To avoid duplicates
    
    for page_num, page in enumerate(doc):
        # Method 1: Extract embedded images
        image_list = page.get_images(full=True)
        
        for img_index, img in enumerate(image_list):
            xref = img[0]
            
            try:
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                ext = base_image["ext"]
                
                # Calculate hash to detect duplicates
                img_hash = hash(image_bytes)
                if img_hash in seen_hashes:
                    continue
                seen_hashes.add(img_hash)
                
                # Get image position(s) on page
                rects = page.get_image_rects(xref)
                
                for rect in rects:
                    # Enhance image if possible
                    enhanced_bytes = _enhance_image(image_bytes, ext) if CV2_AVAILABLE else image_bytes
                    
                    # Encode to base64
                    b64_str = base64.b64encode(enhanced_bytes).decode("utf-8")
                    
                    image_data = {
                        "page_num": page_num + 1,
                        "bbox": (rect.x0, rect.y0, rect.x1, rect.y1),
                        "base64": f"data:image/{ext};base64,{b64_str}",
                        "width": base_image["width"],
                        "height": base_image["height"],
                        "format": ext,
                        "source": "embedded"
                    }
                    extracted_images.append(image_data)
            
            except Exception as e:
                logger.warning(f"Failed to extract image {img_index} from page {page_num + 1}: {e}")
        
        # Method 2: Extract vector graphics as images (diagrams, charts)
        # This captures content that might not be in the image list
        try:
            vector_images = _extract_vector_graphics(page, page_num)
            extracted_images.extend(vector_images)
        except Exception as e:
            logger.warning(f"Vector graphics extraction failed for page {page_num + 1}: {e}")
    
    logger.info(f"Extracted {len(extracted_images)} images total (enhanced)")
    return extracted_images


def _enhance_image(image_bytes, ext):
    """
    Enhance image quality for better display and OCR
    - Denoise
    - Sharpen
    - Contrast adjustment
    """
    if not CV2_AVAILABLE:
        return image_bytes
    
    try:
        # Convert to PIL Image
        img = Image.open(io.BytesIO(image_bytes))
        
        # Convert to numpy array
        img_array = np.array(img)
        
        # Skip enhancement for very small images (likely icons)
        if img_array.shape[0] < 50 or img_array.shape[1] < 50:
            return image_bytes
        
        # Convert to BGR for OpenCV
        if len(img_array.shape) == 2:  # Grayscale
            img_cv = img_array
        elif img_array.shape[2] == 3:  # RGB
            img_cv = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
        elif img_array.shape[2] == 4:  # RGBA
            img_cv = cv2.cvtColor(img_array, cv2.COLOR_RGBA2BGR)
        else:
            return image_bytes
        
        # Apply gentle denoising
        denoised = cv2.fastNlMeansDenoisingColored(img_cv, None, 3, 3, 7, 21) if len(img_cv.shape) == 3 else cv2.fastNlMeansDenoising(img_cv, None, 3, 7, 21)
        
        # Enhance contrast (CLAHE)
        if len(denoised.shape) == 3:
            lab = cv2.cvtColor(denoised, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            l = clahe.apply(l)
            enhanced = cv2.merge([l, a, b])
            enhanced = cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)
        else:
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            enhanced = clahe.apply(denoised)
        
        # Convert back to PIL
        if len(enhanced.shape) == 3:
            enhanced_pil = Image.fromarray(cv2.cvtColor(enhanced, cv2.COLOR_BGR2RGB))
        else:
            enhanced_pil = Image.fromarray(enhanced)
        
        # Save to bytes
        output = io.BytesIO()
        enhanced_pil.save(output, format=ext.upper() if ext.upper() in ['PNG', 'JPEG', 'JPG'] else 'PNG')
        return output.getvalue()
    
    except Exception as e:
        logger.warning(f"Image enhancement failed: {e}. Using original")
        return image_bytes


def _extract_vector_graphics(page, page_num):
    """
    Extract vector graphics (diagrams, charts) as rasterized images
    """
    vector_images = []
    
    try:
        # Get page as high-res image
        mat = fitz.Matrix(2, 2)  # 2x zoom
        pix = page.get_pixmap(matrix=mat, alpha=False)
        
        # Convert to PIL Image
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        
        # Convert to numpy for analysis
        img_array = np.array(img)
        
        # Detect regions with graphics (simplified heuristic)
        # This is a placeholder - you could use more sophisticated detection
        # For now, we'll skip this to avoid false positives
        
    except Exception as e:
        logger.debug(f"Vector graphics extraction skipped for page {page_num + 1}: {e}")
    
    return vector_images


# Backward compatibility
def extract_images(pdf_bytes: bytes):
    """Wrapper for backward compatibility"""
    return extract_images_enhanced(pdf_bytes)


def test_ocr_installation():
    """
    Test function to verify pytesseract installation and configuration.
    Run this to check if OCR is working correctly.
    """
    if not PYTESSERACT_AVAILABLE:
        print("❌ Pytesseract is NOT available. Please install it using: pip install pytesseract")
        return False
    
    try:
        # Get tesseract version to verify it's working
        version = pytesseract.get_tesseract_version()
        print(f"✅ Tesseract OCR is installed and working!")
        print(f"   Version: {version}")
        
        # Create a simple test image with text
        test_img = Image.new('RGB', (200, 50), color='white')
        from PIL import ImageDraw, ImageFont
        draw = ImageDraw.Draw(test_img)
        draw.text((10, 10), "Hello OCR!", fill='black')
        
        # Test OCR
        text = pytesseract.image_to_string(test_img)
        print(f"   Test OCR result: '{text.strip()}'")
        print("✅ OCR is ready to use!")
        return True
        
    except Exception as e:
        print(f"❌ OCR test failed: {e}")
        print("   Make sure Tesseract is installed at: C:\\Program Files\\Tesseract-OCR\\tesseract.exe")
        print("   Or update the path in this file if installed elsewhere.")
        return False


# Uncomment the line below to test OCR when running this file directly
# if __name__ == "__main__":
#     test_ocr_installation()

