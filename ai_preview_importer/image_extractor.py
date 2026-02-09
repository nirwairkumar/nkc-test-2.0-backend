import fitz
import io
import base64
from utils.logger import get_logger

logger = get_logger(__name__)

def extract_images(pdf_bytes: bytes):
    """
    Extracts images from PDF bytes.
    Returns a list of images with metadata.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    extracted_images = []
    
    for page_num, page in enumerate(doc):
        image_list = page.get_images(full=True)
        # logger.info(f"Page {page_num+1}: Found {len(image_list)} images")
        
        for img_index, img in enumerate(image_list):
            xref = img[0]
            base_image = doc.extract_image(xref)
            image_bytes = base_image["image"]
            ext = base_image["ext"]
            
            # Get image bbox on page
            # Note: This finds the first instance of the image on the page
            rects = page.get_image_rects(xref)
            
            for rect in rects:
                # Encode to base64
                b64_str = base64.b64encode(image_bytes).decode("utf-8")
                
                image_data = {
                    "page_num": page_num + 1,
                    "bbox": (rect.x0, rect.y0, rect.x1, rect.y1),
                    "base64": f"data:image/{ext};base64,{b64_str}",
                    "width": base_image["width"],
                    "height": base_image["height"]
                }
                extracted_images.append(image_data)
                
    logger.info(f"Extracted {len(extracted_images)} images total")
    return extracted_images
