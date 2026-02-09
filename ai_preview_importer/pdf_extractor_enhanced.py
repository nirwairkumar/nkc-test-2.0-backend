"""
Enhanced PDF Extractor with Multi-Tool Approach
Uses PyMuPDF, pdfplumber, OCR, and advanced image processing
"""
import fitz  # PyMuPDF
import pdfplumber
import io
import re
import numpy as np
from PIL import Image
from utils.logger import get_logger

logger = get_logger(__name__)

# Auto-configure OCR
try:
    from utils.ocr_config import configure_tesseract
    configure_tesseract()
except ImportError:
    pass

# Try to import OCR (optional, graceful degradation)
try:
    import pytesseract
    import cv2
    OCR_AVAILABLE = True
    logger.info("OCR (Tesseract) is available")
except ImportError:
    OCR_AVAILABLE = False
    logger.warning("OCR not available. Install pytesseract and opencv-python for scanned PDF support")

def extract_text_blocks_enhanced(pdf_bytes: bytes):
    """
    Enhanced text extraction using multiple methods:
    1. PyMuPDF (primary) - fast and accurate for digital PDFs
    2. pdfplumber (fallback) - better for tables and complex layouts
    3. OCR (last resort) - for scanned/image-based PDFs
    
    Returns a sorted list of lines with metadata (page_num, bbox, text).
    """
    doc_fitz = fitz.open(stream=pdf_bytes, filetype="pdf")
    logger.info(f"Opened PDF with {len(doc_fitz)} pages")
    
    extracted_lines = []
    
    # Also open with pdfplumber for comparison
    pdf_file = io.BytesIO(pdf_bytes)
    
    try:
        with pdfplumber.open(pdf_file) as pdf_plumber:
            for page_num in range(len(doc_fitz)):
                page_fitz = doc_fitz[page_num]
                
                # Method 1: PyMuPDF extraction (primary)
                fitz_lines = _extract_with_pymupdf(page_fitz, page_num)
                
                # Method 2: pdfplumber extraction (for validation/enhancement)
                plumber_page = pdf_plumber.pages[page_num] if page_num < len(pdf_plumber.pages) else None
                plumber_lines = _extract_with_pdfplumber(plumber_page, page_num) if plumber_page else []
                
                # Method 3: OCR fallback (if no text found)
                if not fitz_lines and not plumber_lines and OCR_AVAILABLE:
                    logger.warning(f"Page {page_num + 1}: No text found with standard methods. Trying OCR...")
                    ocr_lines = _extract_with_ocr(page_fitz, page_num)
                    extracted_lines.extend(ocr_lines)
                else:
                    # Merge results (prefer PyMuPDF, supplement with pdfplumber)
                    merged_lines = _merge_extraction_results(fitz_lines, plumber_lines)
                    extracted_lines.extend(merged_lines)
    
    except Exception as e:
        logger.error(f"pdfplumber failed: {e}. Falling back to PyMuPDF only")
        # Fallback to PyMuPDF only
        for page_num, page in enumerate(doc_fitz):
            fitz_lines = _extract_with_pymupdf(page, page_num)
            extracted_lines.extend(fitz_lines)
    
    # Sort ALL extracted lines by reading order
    extracted_lines.sort(key=lambda x: (x["page_num"], x["bbox"][1], x["bbox"][0]))
    
    logger.info(f"Extracted {len(extracted_lines)} text lines from PDF (enhanced)")
    return extracted_lines


def _extract_with_pymupdf(page, page_num):
    """Extract text using PyMuPDF with line-level geometry"""
    lines = []
    page_dict = page.get_text("dict")
    blocks = page_dict.get("blocks", [])
    
    for block in blocks:
        if block.get("type") == 0:  # Text block
            for line in block.get("lines", []):
                line_text = "".join([span["text"] for span in line.get("spans", [])])
                
                if line_text.strip():  # Only non-empty lines
                    line_data = {
                        "page_num": page_num + 1,
                        "bbox": line["bbox"],
                        "text": line_text,
                        "source": "pymupdf"
                    }
                    lines.append(line_data)
    
    return lines


def _extract_with_pdfplumber(page, page_num):
    """Extract text using pdfplumber (better for tables)"""
    lines = []
    
    try:
        # Extract words with positions
        words = page.extract_words(keep_blank_chars=True)
        
        if not words:
            return lines
        
        # Group words into lines based on y-coordinate proximity
        current_line = []
        current_y = None
        y_tolerance = 3  # pixels
        
        for word in words:
            word_y = word['top']
            
            if current_y is None or abs(word_y - current_y) <= y_tolerance:
                current_line.append(word)
                current_y = word_y
            else:
                # Save current line
                if current_line:
                    line_text = " ".join([w['text'] for w in current_line])
                    bbox = _calculate_bbox_from_words(current_line)
                    lines.append({
                        "page_num": page_num + 1,
                        "bbox": bbox,
                        "text": line_text,
                        "source": "pdfplumber"
                    })
                
                # Start new line
                current_line = [word]
                current_y = word_y
        
        # Don't forget the last line
        if current_line:
            line_text = " ".join([w['text'] for w in current_line])
            bbox = _calculate_bbox_from_words(current_line)
            lines.append({
                "page_num": page_num + 1,
                "bbox": bbox,
                "text": line_text,
                "source": "pdfplumber"
            })
    
    except Exception as e:
        logger.warning(f"pdfplumber extraction failed for page {page_num + 1}: {e}")
    
    return lines


def _extract_with_ocr(page, page_num):
    """Extract text using OCR (for scanned PDFs)"""
    lines = []
    
    if not OCR_AVAILABLE:
        return lines
    
    try:
        # Convert page to image
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x zoom for better OCR
        img_data = pix.tobytes("png")
        
        # Convert to PIL Image
        img = Image.open(io.BytesIO(img_data))
        
        # Convert to OpenCV format for preprocessing
        img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        
        # Preprocess image for better OCR
        gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
        # Apply thresholding
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # OCR with bounding box data
        ocr_data = pytesseract.image_to_data(thresh, output_type=pytesseract.Output.DICT)
        
        # Group by line
        current_line_num = None
        current_line_words = []
        current_line_boxes = []
        
        for i in range(len(ocr_data['text'])):
            text = ocr_data['text'][i].strip()
            conf = int(ocr_data['conf'][i])
            
            if conf > 30 and text:  # Only confident detections
                line_num = ocr_data['line_num'][i]
                
                if current_line_num is None or line_num == current_line_num:
                    current_line_words.append(text)
                    current_line_boxes.append({
                        'x': ocr_data['left'][i] / 2,  # Adjust for 2x zoom
                        'y': ocr_data['top'][i] / 2,
                        'w': ocr_data['width'][i] / 2,
                        'h': ocr_data['height'][i] / 2
                    })
                    current_line_num = line_num
                else:
                    # Save previous line
                    if current_line_words:
                        line_text = " ".join(current_line_words)
                        bbox = _calculate_bbox_from_ocr_boxes(current_line_boxes)
                        lines.append({
                            "page_num": page_num + 1,
                            "bbox": bbox,
                            "text": line_text,
                            "source": "ocr"
                        })
                    
                    # Start new line
                    current_line_words = [text]
                    current_line_boxes = [{
                        'x': ocr_data['left'][i] / 2,
                        'y': ocr_data['top'][i] / 2,
                        'w': ocr_data['width'][i] / 2,
                        'h': ocr_data['height'][i] / 2
                    }]
                    current_line_num = line_num
        
        # Don't forget the last line
        if current_line_words:
            line_text = " ".join(current_line_words)
            bbox = _calculate_bbox_from_ocr_boxes(current_line_boxes)
            lines.append({
                "page_num": page_num + 1,
                "bbox": bbox,
                "text": line_text,
                "source": "ocr"
            })
        
        logger.info(f"OCR extracted {len(lines)} lines from page {page_num + 1}")
    
    except Exception as e:
        logger.error(f"OCR failed for page {page_num + 1}: {e}")
    
    return lines


def _merge_extraction_results(fitz_lines, plumber_lines):
    """
    Merge results from multiple extractors.
    Prefer PyMuPDF, but add unique content from pdfplumber.
    """
    if not plumber_lines:
        return fitz_lines
    
    if not fitz_lines:
        return plumber_lines
    
    # For now, prefer PyMuPDF (it's more reliable for most PDFs)
    # TODO: Implement smart merging based on content comparison
    return fitz_lines


def _calculate_bbox_from_words(words):
    """Calculate bounding box from pdfplumber words"""
    x0 = min(w['x0'] for w in words)
    y0 = min(w['top'] for w in words)
    x1 = max(w['x1'] for w in words)
    y1 = max(w['bottom'] for w in words)
    return (x0, y0, x1, y1)


def _calculate_bbox_from_ocr_boxes(boxes):
    """Calculate bounding box from OCR boxes"""
    x0 = min(b['x'] for b in boxes)
    y0 = min(b['y'] for b in boxes)
    x1 = max(b['x'] + b['w'] for b in boxes)
    y1 = max(b['y'] + b['h'] for b in boxes)
    return (x0, y0, x1, y1)


# Keep the original functions for backward compatibility
def extract_text_blocks(pdf_bytes: bytes):
    """Wrapper for backward compatibility"""
    return extract_text_blocks_enhanced(pdf_bytes)




# Question detection and formatting functions (copied to avoid circular import)
def detect_question_anchors(lines):
    """
    Groups sorted text lines into questions based on regex anchors.
    Returns a list of question objects with merged bboxes.
    """
    anchor_pattern = re.compile(r'^\s*(?:\d+\.|Q\.?\s*\d+|Question\s*\d+)\s', re.IGNORECASE)
    ignore_pattern = re.compile(r'^\s*(?:Page\s*\d+|\d+\s*$|Copyright|Institute)', re.IGNORECASE)
    
    questions = []
    current_question = None
    
    for line in lines:
        text = line['text']
        
        if ignore_pattern.match(text):
            continue
        
        if anchor_pattern.match(text):
            if current_question:
                current_question['question_bbox'] = _calculate_union_bbox(current_question['lines'])
                questions.append(current_question)
            
            current_question = {
                "question_index": len(questions) + 1,
                "lines": [line],
                "question_bbox": line['bbox']
            }
        else:
            if current_question:
                current_question['lines'].append(line)
    
    if current_question:
        current_question['question_bbox'] = _calculate_union_bbox(current_question['lines'])
        questions.append(current_question)
    
    return questions


def _calculate_union_bbox(lines):
    """Calculate union bounding box from multiple lines"""
    if not lines:
        return (0, 0, 0, 0)
    
    x0s = [l['bbox'][0] for l in lines]
    y0s = [l['bbox'][1] for l in lines]
    x1s = [l['bbox'][2] for l in lines]
    y1s = [l['bbox'][3] for l in lines]
    
    return (min(x0s), min(y0s), max(x1s), max(y1s))


def attach_images_to_questions(questions, images):
    """Attach images to questions based on geometry"""
    images_by_page = {}
    for img in images:
        p = img['page_num']
        if p not in images_by_page:
            images_by_page[p] = []
        images_by_page[p].append(img)
    
    questions_by_page = {}
    for q in questions:
        if not q['lines']:
            continue
        p = q['lines'][0]['page_num']
        if p not in questions_by_page:
            questions_by_page[p] = []
        questions_by_page[p].append(q)
    
    for page_num, page_imgs in images_by_page.items():
        page_qs = questions_by_page.get(page_num, [])
        if not page_qs:
            continue
        
        for i, img in enumerate(page_imgs):
            img_id = f"IMG_{i}"
            img['id'] = img_id
            
            img_bbox = img['bbox']
            img_y_center = (img_bbox[1] + img_bbox[3]) / 2
            
            best_q = None
            min_dist = float('inf')
            candidate_container = None
            
            for q in page_qs:
                q_bbox = q['question_bbox']
                if q_bbox[1] <= img_y_center <= q_bbox[3]:
                    candidate_container = q
                    break
            
            if candidate_container:
                best_q = candidate_container
            else:
                for q in page_qs:
                    q_bbox = q['question_bbox']
                    if q_bbox[3] <= img_bbox[1]:
                        dist = img_bbox[1] - q_bbox[3]
                        if dist < min_dist:
                            min_dist = dist
                            best_q = q
            
            if best_q:
                best_q['image_id'] = img_id


def format_questions_for_ai(questions):
    """Transform internal question objects into AI-ready structure"""
    ai_ready_questions = []
    opt_pattern = re.compile(r'^\s*(?:[A-D]\.|[A-D]\)|\([A-D]\))\s', re.IGNORECASE)
    
    for q in questions:
        raw_lines = []
        options = {"A": None, "B": None, "C": None, "D": None}
        current_opt = None
        
        for line in q['lines']:
            text = line['text']
            match = opt_pattern.match(text)
            
            if match:
                clean_start = match.group(0).strip().upper()
                letter_match = re.search(r'[A-D]', clean_start)
                if letter_match:
                    current_opt = letter_match.group(0)
                    options[current_opt] = text
                else:
                    raw_lines.append(text)
            else:
                if current_opt:
                    if options[current_opt]:
                        options[current_opt] += " " + text
                    else:
                        options[current_opt] = text
                else:
                    raw_lines.append(text)
        
        q_obj = {
            "id": q['question_index'],
            "raw_question_lines": raw_lines,
            "options": options,
            "image_id": q.get('image_id'),
            "needsAnswer": True
        }
        ai_ready_questions.append(q_obj)
    
    return ai_ready_questions

