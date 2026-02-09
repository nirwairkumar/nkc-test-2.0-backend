import fitz
from utils.logger import get_logger

logger = get_logger(__name__)

def extract_text_blocks(pdf_bytes: bytes):
    """
    Extracts text lines from PDF bytes using PyMuPDF (fitz) with line-level geometry.
    Returns a sorted list of lines with metadata (page_num, bbox, text).
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    logger.info(f"Opened PDF with {len(doc)} pages")
    
    extracted_lines = []
    
    for page_num, page in enumerate(doc):
        # Use "dict" to get line-level details
        page_dict = page.get_text("dict")
        blocks = page_dict.get("blocks", [])
        
        for block in blocks:
            # Type 0 is text
            if block.get("type") == 0:
                for line in block.get("lines", []):
                    # Merge spans into one string, preserving original text
                    line_text = "".join([span["text"] for span in line.get("spans", [])])
                    
                    if line_text: # Keep whitespace lines if meaningful, but typically we might want to strip? 
                                  # Instruction says "Preserve original text (no rewriting)". 
                                  # I will not strip aggressively inside the join, but maybe check if empty?
                                  # "Merge all spans into one string" -> "text": string.
                        
                        line_data = {
                            "page_num": page_num + 1,
                            "bbox": line["bbox"], # (x0, y0, x1, y1)
                            "text": line_text
                        }
                        extracted_lines.append(line_data)
                
    # Sort ALL extracted lines by reading order:
    # First by page, then y-coordinate, then x-coordinate
    # (x0, y0, x1, y1) -> y0 is index 1, x0 is index 0
    extracted_lines.sort(key=lambda x: (x["page_num"], x["bbox"][1], x["bbox"][0]))
                
    logger.info(f"Extracted {len(extracted_lines)} text lines from PDF")
    return extracted_lines

import re

def detect_question_anchors(lines):
    """
    Groups sorted text lines into questions based on regex anchors.
    Sorts lines by reading order before grouping.
    Returns a list of question objects with merged bboxes.
    """
    # Regex patterns for question anchors
    # 1. Starts with "1.", "10."
    # 2. Starts with "Q.1", "Q. 1", "Q1"
    # 3. Starts with "Question 1", "Question1"
    anchor_pattern = re.compile(r'^\s*(?:\d+\.|Q\.?\s*\d+|Question\s*\d+)\s', re.IGNORECASE)

    # Patterns to ignore (headers/footers)
    # Page numbers alone, Copyright, Institute names (generic heuristic)
    ignore_pattern = re.compile(r'^\s*(?:Page\s*\d+|\d+\s*$|Copyright|Institute)', re.IGNORECASE)

    questions = []
    current_question = None

    for line in lines:
        text = line['text']

        # 1. Skip Headers/Footers
        if ignore_pattern.match(text):
            continue

        # 2. Check for Anchor
        if anchor_pattern.match(text):
            # Start new question
            # If we had a current question, calculate its final bbox and push it
            if current_question:
                # Close previous question
                current_question['question_bbox'] = _calculate_union_bbox(current_question['lines'])
                questions.append(current_question)
            
            # Init new question
            current_question = {
                "question_index": len(questions) + 1,
                "lines": [line],
                "question_bbox": line['bbox'] # Initial bbox
            }
        else:
            # 3. No Anchor - Append to current or ignore (if no question started yet)
            if current_question:
                current_question['lines'].append(line)
            # else: Ignore content before first question (e.g. Test Title, Instructions)

    # Append the last question
    if current_question:
        current_question['question_bbox'] = _calculate_union_bbox(current_question['lines'])
        questions.append(current_question)

    return questions

def _calculate_union_bbox(lines):
    if not lines:
        return (0,0,0,0)
    
    x0s = [l['bbox'][0] for l in lines]
    y0s = [l['bbox'][1] for l in lines]
    x1s = [l['bbox'][2] for l in lines]
    y1s = [l['bbox'][3] for l in lines]
    
    return (min(x0s), min(y0s), max(x1s), max(y1s))

def attach_images_to_questions(questions, images):
    """
    Attaches images to questions based on geometry.
    - Assigns IDs to images (IMG_0, IMG_1...) per page.
    - Maps image to the Nearest Question that contains it or is immediately above it.
    - Mutates question objects to add 'image_id'.
    - Returns None (modifies in-place).
    """
    # Group by page for processing
    images_by_page = {}
    for img in images:
        p = img['page_num']
        if p not in images_by_page: images_by_page[p] = []
        images_by_page[p].append(img)
    
    questions_by_page = {}
    for q in questions:
        # determining page from first line (heuristic)
        if not q['lines']: continue
        p = q['lines'][0]['page_num']
        if p not in questions_by_page: questions_by_page[p] = []
        questions_by_page[p].append(q)

    # Process per page
    for page_num, page_imgs in images_by_page.items():
        page_qs = questions_by_page.get(page_num, [])
        if not page_qs:
            continue
            
        # Sort questions by Y position for binary search / proximity checks
        # They should already be sorted by reading order (which is primary Y), but let's be safe
        # page_qs.sort(key=lambda q: q['question_bbox'][1]) 
        # Actually they are sorted by detect_question_anchors return order which follows line order.
        
        for i, img in enumerate(page_imgs):
            # 1. Assign ID (Context: 'IMG_3')
            # Assuming per-page 0-based index matches downstream pipeline
            img_id = f"IMG_{i}"
            img['id'] = img_id # Store for reference
            
            # 2. Geometry Check
            img_bbox = img['bbox'] # x0, y0, x1, y1
            img_y_center = (img_bbox[1] + img_bbox[3]) / 2
            
            best_q = None
            min_dist = float('inf')
            
            # Strategy:
            # A. Inside: Image Y center is between Q Y top and Q Y bottom
            # B. Below: Image is below Q. (Q Y bottom < Image Y Top) -> Find nearest.
            
            # Priority: strict containment > nearest above
            
            candidate_container = None
            
            for q in page_qs:
                q_bbox = q['question_bbox']
                # Check Containment (Vertical overlap)
                if q_bbox[1] <= img_y_center <= q_bbox[3]:
                    # If multiple contain it (nested?), logic says "attach to ONE".
                    # Usually questions don't overlap. First one is fine?
                    candidate_container = q
                    break # Found container
            
            if candidate_container:
                best_q = candidate_container
            else:
                # Find Nearest Above
                # We want q where q_bbox[3] (bottom) <= img_bbox[1] (top)
                # And maximize q_bbox[3] (closest to image top)
                for q in page_qs:
                    q_bbox = q['question_bbox']
                    if q_bbox[3] <= img_bbox[1]: # Question is above image
                        dist = img_bbox[1] - q_bbox[3]
                        if dist < min_dist:
                            min_dist = dist
                            best_q = q
            
            # 3. Attach
            if best_q:
                # "Each image MUST attach to only ONE question" - Loop ensures we process image once.
                # "NEVER attach the same image to multiple questions" - Implied by logic.
                # Note: A question might receive multiple images this way.
                # "question.image_id = 'IMG_3'" -> Singular? 
                # If we overwrite, we lose previous images. Prompt implies singular field.
                # If a question already has an image, should we overwrite?
                # But instruction is "Store image reference ID on question".
                # I will overwrite for now as per strict instruction syntax.
                best_q['image_id'] = img_id

def format_questions_for_ai(questions):
    """
    Transforms internal question objects into final AI-ready structure.
    Parses options (A, B, C, D) from lines using deterministic regex.
    """
    ai_ready_questions = []
    
    # Regex for Option Starts: "A.", "A)", "(A)", "a.", "a)", "(a)"
    # STRICTLY looking for A-D range as per standard exams.
    opt_pattern = re.compile(r'^\s*(?:[A-D]\.|[A-D]\)|\([A-D]\))\s', re.IGNORECASE)
    
    for q in questions:
        raw_lines = []
        options = {"A": None, "B": None, "C": None, "D": None}
        
        current_opt = None
        
        for line in q['lines']:
            text = line['text']
            # strip? logic says "Do NOT rewrite text", but purely for regex checking we might need clean text.
            # We will store the original text in the object.
            
            match = opt_pattern.match(text)
            if match:
                # Identified an option start
                # Determine which letter
                # We can extract the letter from the text.
                # match.group() might be "A. "
                # Let's clean it to find the letter.
                clean_start = match.group(0).strip().upper() 
                # clean_start could be "A.", "A)", "(A)"
                # Just grab the first char that is a letter
                letter_match = re.search(r'[A-D]', clean_start)
                if letter_match:
                    current_opt = letter_match.group(0) # "A"
                    # Store text. Should we remove the label? "Do NOT rewrite text" usually applies to the core content.
                    # Standard practice for "options" text is to exclude the "A." label if we are structuring it.
                    # BUT "Do NOT rewrite text" is a strong rule.
                    # However, "raw_question_lines" implies the question text.
                    # If I leave "A. Option Text" in options["A"], that is safer given "Do NOT rewrite".
                    options[current_opt] = text
                else:
                    # Fallback, treat as question text if we can't parse letter (unlikely with regex)
                    raw_lines.append(text)
            else:
                # Not an option start
                if current_opt:
                    # Continuation of previous option?
                    # "Line-level geometry".
                    # If we are in an option, append to it?
                    # Simple heuristic: If we started options, append to current option.
                    # If we haven't started options, it's question text.
                    if options[current_opt]:
                        options[current_opt] += " " + text
                    else:
                        options[current_opt] = text
                else:
                    raw_lines.append(text)
        
        # Construct Final Object
        q_obj = {
            "id": q['question_index'],
            "raw_question_lines": raw_lines,
            "options": options,
            "image_id": q.get('image_id'), # might be None
            "needsAnswer": True # Explicitly requested
        }
        
        ai_ready_questions.append(q_obj)

    return ai_ready_questions
