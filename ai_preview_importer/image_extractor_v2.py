"""
Enhanced Image Extractor V2 - Advanced extraction with classification
Uses Python libraries: PyMuPDF, PIL, OpenCV, NumPy
"""
import fitz
import io
import base64
import numpy as np
from PIL import Image
from typing import List, Dict
from utils.logger import get_logger
from ai_preview_importer.diagram_detector import detect_and_extract_diagrams

logger = get_logger(__name__)

# Try to import OpenCV
try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    logger.warning("OpenCV not available. Image enhancement disabled")


def extract_all_visual_elements(pdf_bytes: bytes) -> List[Dict]:
    """
    Extracts ALL visual elements from PDF:
    - Embedded images
    - Vector graphics/diagrams
    - Mathematical equations
    - Charts and graphs
    
    Returns list of image objects with metadata and classification.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    all_images = []
    seen_hashes = set()
    
    # Method 1: Extract embedded images
    for page_num, page in enumerate(doc):
        image_list = page.get_images(full=True)
        
        for img_index, img in enumerate(image_list):
            xref = img[0]
            
            try:
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                ext = base_image["ext"]
                
                # Deduplicate
                img_hash = hash(image_bytes)
                if img_hash in seen_hashes:
                    continue
                seen_hashes.add(img_hash)
                
                # Get image positions
                rects = page.get_image_rects(xref)
                
                for rect in rects:
                    # Enhance image if possible
                    enhanced_bytes = _enhance_image_quality(image_bytes, ext) if CV2_AVAILABLE else image_bytes
                    
                    # Encode to base64
                    b64_str = base64.b64encode(enhanced_bytes).decode("utf-8")
                    
                    # Classify image type
                    img_type = _classify_image_type(enhanced_bytes, ext)
                    
                    image_data = {
                        "id": f"img_{page_num}_{img_index}",
                        "page_num": page_num + 1,
                        "bbox": (rect.x0, rect.y0, rect.x1, rect.y1),
                        "base64": f"data:image/{ext};base64,{b64_str}",
                        "width": base_image["width"],
                        "height": base_image["height"],
                        "format": ext,
                        "type": img_type,
                        "source": "embedded"
                    }
                    all_images.append(image_data)
            
            except Exception as e:
                logger.warning(f"Failed to extract image {img_index} from page {page_num + 1}: {e}")
    
    # Method 2: Extract diagrams and vector graphics
    try:
        diagrams = detect_and_extract_diagrams(pdf_bytes)
        
        # Add unique IDs to diagrams
        for i, diagram in enumerate(diagrams):
            diagram['id'] = f"diagram_{diagram['page_num']}_{i}"
        
        all_images.extend(diagrams)
    except Exception as e:
        logger.warning(f"Diagram extraction failed: {e}")
    
    logger.info(f"Extracted {len(all_images)} total visual elements")
    return all_images


def _enhance_image_quality(image_bytes: bytes, ext: str) -> bytes:
    """
    Enhance image quality using OpenCV.
    - Denoise
    - Sharpen
    - Contrast adjustment
    """
    if not CV2_AVAILABLE:
        return image_bytes
    
    try:
        # Convert to PIL Image
        img = Image.open(io.BytesIO(image_bytes))
        
        # Skip very small images
        if img.width < 50 or img.height < 50:
            return image_bytes
        
        # Convert to numpy array
        img_array = np.array(img)
        
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
        if len(img_cv.shape) == 3:
            denoised = cv2.fastNlMeansDenoisingColored(img_cv, None, 3, 3, 7, 21)
        else:
            denoised = cv2.fastNlMeansDenoising(img_cv, None, 3, 7, 21)
        
        # Sharpen slightly
        kernel = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
        sharpened = cv2.filter2D(denoised, -1, kernel * 0.1)
        
        # Convert back to PIL
        if len(sharpened.shape) == 3:
            enhanced_pil = Image.fromarray(cv2.cvtColor(sharpened, cv2.COLOR_BGR2RGB))
        else:
            enhanced_pil = Image.fromarray(sharpened)
        
        # Save to bytes
        output = io.BytesIO()
        enhanced_pil.save(output, format=ext.upper() if ext.upper() in ['PNG', 'JPEG', 'JPG'] else 'PNG')
        return output.getvalue()
    
    except Exception as e:
        logger.debug(f"Image enhancement failed: {e}. Using original")
        return image_bytes


def _classify_image_type(image_bytes: bytes, ext: str) -> str:
    """
    Classify image type: 'photo', 'diagram', 'chart', 'equation', 'icon'
    """
    try:
        img = Image.open(io.BytesIO(image_bytes))
        width, height = img.size
        
        # Very small images are likely icons
        if width < 50 or height < 50:
            return 'icon'
        
        # Convert to numpy for analysis
        img_array = np.array(img)
        
        # Calculate color diversity
        if len(img_array.shape) == 3:
            unique_colors = len(np.unique(img_array.reshape(-1, img_array.shape[2]), axis=0))
        else:
            unique_colors = len(np.unique(img_array))
        
        # Low color diversity suggests diagram/chart
        if unique_colors < 50:
            return 'diagram'
        elif unique_colors < 200:
            return 'chart'
        else:
            return 'photo'
    
    except Exception as e:
        logger.debug(f"Image classification failed: {e}")
        return 'unknown'


# Backward compatibility
def extract_images_v2(pdf_bytes: bytes) -> List[Dict]:
    """Wrapper for backward compatibility."""
    return extract_all_visual_elements(pdf_bytes)
