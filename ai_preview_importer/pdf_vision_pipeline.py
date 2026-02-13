"""
PDF Vision Pipeline - Full-page vision approach using Gemini
Replaces the fragmented text-block + spatial-analysis pipeline with a simple,
accurate approach: render pages as images → send to Gemini Vision → parse results.

Supports two modes:
  - "extract": Extract exact questions from the exam paper as-is
  - "generate": Create new original MCQs based on the PDF content
  
Now also supports:
  - Multiple image files (not just PDFs)
  - Answer key processing for automatic correct answer matching
  - Intelligent answer detection within documents
  - Cross-page question stitching
"""
import os
import io
import re
import json
import base64
import fitz  # PyMuPDF
import google.generativeai as genai
from typing import Dict, List, Optional, Tuple
from utils.logger import get_logger
from app.core.config import settings
from PIL import Image

logger = get_logger(__name__)

# Configure Gemini using the app settings (loaded from .env)
api_key = settings.GEMINI_API_KEY
if api_key:
    genai.configure(api_key=api_key)
else:
    logger.warning("GEMINI_API_KEY not found in settings/.env")


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

EXTRACT_PROMPT = """
ROLE:
You are an AI document parser, OCR analyst, and exam-content extractor.

GOAL:
Convert the PROVIDED document pages/images into a STRICT, VALID JSON test file.
DO NOT generate new questions.
ONLY extract and restructure content that exists in the file.

CRITICAL BEHAVIOR RULES:
- Read the uploaded pages/images visually (OCR + layout reasoning).
- Identify QUESTIONS, OPTIONS, ANSWERS, and IMAGES based on layout.
- If a diagram/image appears immediately before or after a question, note the page number.
- NEVER hallucinate or invent content.
- If something is unclear, infer conservatively from the document layout.
- Output ONLY valid JSON. No markdown. No explanations. No comments.

--------------------------------------------------
QUESTION TYPE DETECTION (CRITICAL):
For EACH question, you MUST detect the type based on these indicators:

1. SINGLE CHOICE (type: "single"):
   - Has options A, B, C, D (or 1, 2, 3, 4)
   - Instructions say "Select ONE" or similar
   - Answer key shows single letter/number
   - Most common type - use this as DEFAULT if unclear

2. MULTIPLE CHOICE (type: "multiple"):
   - Has options A, B, C, D
   - Instructions say "Select ALL that apply", "Choose one or more", "Multiple correct"
   - Answer key shows multiple letters like "A, C" or "B, D"
   - Checkboxes instead of radio buttons

3. NUMERICAL (type: "numerical"):
   - NO options A/B/C/D
   - Asks for a numerical value, calculation result
   - Has answer like "3.14" or range "2.5 to 3.5"
   - Fill-in-the-blank with numbers

--------------------------------------------------
CROSS-PAGE QUESTION HANDLING (CRITICAL):
When processing multiple pages, you MUST handle questions that span across pages:

1. DETECT split questions:
   - If a question starts on page N but options/answer continue on page N+1
   - If question text ends abruptly at page bottom and continues on next page
   - Look for question numbers to identify continuity

2. MERGE split questions:
   - COMBINE question text from all pages into ONE complete question
   - COMBINE all options (A, B, C, D) even if spread across pages
   - Preserve the single question number (e.g., "Question 5")
   - Set diagramPage to the page where the diagram appears

3. NEVER create duplicate questions:
   - Do NOT create two Question 5 entries if it spans 2 pages
   - Use the SAME question ID for the merged question
   - Mark crossPage: true in the output for questions that span multiple pages

4. ANSWER KEY LOCATION:
   - Answers may appear anywhere: inline with questions, at end of page, or separate answer sheet
   - Look for marked answers (checkmarks, bold, circles, "Ans:", "Answer:")
   - Common formats: "Ans: A", "Answer: B", "✓ C", "• D", "5. B" (question 5 answer is B)

--------------------------------------------------
DIAGRAM AND IMAGE EXTRACTION (CRITICAL):
You MUST extract and include ALL diagrams, figures, and images:

1. DETECT diagrams in:
   - Question text area
   - Within options (A, B, C, D)
   - Separate figure references ("Figure 1", "Diagram A")

2. For EACH question, check:
   - Is there a diagram immediately above/below the question?
   - Are there images embedded in the options?
   - Does the question reference a figure/diagram?

3. DIAGRAM TYPES to extract:
   - Mathematical: graphs, curves, geometric shapes, coordinate systems
   - Scientific: chemical structures, physics diagrams, biology illustrations
   - Charts: bar charts, pie charts, line graphs, tables
   - Circuit diagrams, flowcharts, maps, anatomical drawings
   - Small icons/symbols if they are part of the question

4. SIZE HANDLING:
   - Extract diagrams regardless of size (small chemical structures are important!)
   - If diagram is very large, note it but still extract
   - Do NOT filter out images based on size - if it's in the question area, extract it

5. MATCHING:
   - Set "diagramPage" to the page number where the diagram appears
   - If diagram appears in options, note which option (A/B/C/D) in "diagramOption"
   - For multi-part diagrams, reference the main diagram page

--------------------------------------------------
MATHEMATICAL CONTENT EXTRACTION (CRITICAL):
Extract ALL mathematical expressions with HIGH PRECISION:

1. LaTeX Format:
   - Use proper LaTeX syntax: \\frac, \\sqrt, \\int, \\sum, \\prod
   - Escape ALL backslashes for JSON: use \\\\ instead of \\.
   - Inline math: $...$ (e.g., $x^2 + y^2 = z^2$)
   - Block math: $$...$$ for complex equations

2. Common Symbols - TRANSCRIBE CAREFULLY:
   - Fractions: \\frac{numerator}{denominator}
   - Roots: \\sqrt{x}, \\sqrt[3]{x} for cube roots
   - Integrals: \\int, \\oint, \\iint with limits as subscripts/superscripts
   - Sums: \\sum_{i=1}^{n}
   - Limits: \\lim_{x \\to \\infty}
   - Greek letters: \\alpha, \\beta, \\gamma, \\delta, \\theta, \\pi, \\sigma, \\omega
   - Operators: \\pm, \\times, \\div, \\cdot, \\equiv, \\approx, \\neq
   - Arrows: \\rightarrow, \\leftarrow, \\Rightarrow, \\Leftrightarrow
   - Subscripts: x_1, x_{ij}
   - Superscripts: x^2, x^{2n}

3. PRECISION CHECKS:
   - ∫ (integral) vs S
   - α (alpha) vs a
   - β (beta) vs B  
   - θ (theta) vs 0 (zero) or O (letter O)
   - π (pi) vs n
   - μ (mu) vs u
   - ν (nu) vs v
   - ρ (rho) vs p
   - ω (omega) vs w
   - σ (sigma) vs s

4. Complex Expressions:
   - Matrices: Use \\begin{pmatrix} ... \\end{pmatrix}
   - Align equations: Use \\begin{align} ... \\end{align}
   - Piecewise: Use \\begin{cases} ... \\end{cases}

5. VERIFY each mathematical expression by:
   - Reading it back to ensure it makes sense
   - Checking that LaTeX compiles mentally
   - Ensuring no symbols are missing or misidentified

--------------------------------------------------
DOCUMENT ANALYSIS STEPS (MANDATORY):
1. Scan ALL pages first to understand document structure
2. Detect each question boundary using:
   - Question numbers (1, 2, 3... or Q1, Q2, Q3...)
   - Line breaks and spacing
   - Bullets (Q., 1., 1), etc.)
3. For each question:
   - Extract full question text (MERGE if across multiple pages)
   - DETECT TYPE based on indicators above
   - Extract options (A/B/C/D) ONLY for single/multiple choice (COLLECT from all pages)
   - Extract ALL diagrams associated with the question
   - Look for inline answers or markings
4. Detect correct answers using:
   - Answer keys (if provided separately)
   - Highlighted/marked answers within the document
   - End-of-page answer sections
   - Inline markings (bold, checkmarks, circles)
   - Look for patterns like: "1. A", "Q1: B", "Answer: C"
5. Convert all mathematical expressions into LaTeX with HIGH PRECISION.
6. Preserve original wording (do NOT rewrite).
7. FOR PASSAGE/COMPREHENSION QUESTIONS:
   - Extract the passage text ONCE.
   - For EVERY question belonging to that passage, include a "passageContent" field.

--------------------------------------------------
MATH & FORMATTING RULES:
- Use LaTeX for ALL math: \\frac, \\sqrt, \\int, x^2, etc.
- Escape ALL backslashes for JSON: use \\\\ instead of \\.
- Inline math: $...$
- Block math: $$...$$
- Do NOT simplify expressions.

TEXT & LINE-BREAK RULES:
- DO NOT use escaped newline characters or real line breaks inside strings.
- Use <br> tags for line breaks in questions and options.
- Multi-line questions should use <br> tags to separate lines.
- Do NOT use other HTML tags or markdown.

--------------------------------------------------
STRICT JSON OUTPUT FORMAT (DO NOT CHANGE):
{
  "title": "Extracted from document or inferred",
  "description": "Auto-generated from document content",
  "questions": [
    {
      "id": 1,
      "type": "single",
      "question": "Exact extracted question text with LaTeX",
      "diagramPage": null,
      "diagramOption": null,
      "options": {
        "A": "Option text",
        "B": "Option text",
        "C": "Option text",
        "D": "Option text"
      },
      "correctAnswer": "A",
      "marks": 4,
      "negativeMarks": 1,
      "crossPage": false
    }
  ]
}

--------------------------------------------------
ANSWER RULES BY TYPE:
- Single choice: 
  * type: "single"
  * options: { "A": "...", "B": "...", "C": "...", "D": "..." }
  * correctAnswer: "A" (single string)

- Multiple choice:
  * type: "multiple" 
  * options: { "A": "...", "B": "...", "C": "...", "D": "..." }
  * correctAnswer: ["A", "C"] (array of strings)

- Numerical:
  * type: "numerical"
  * options: null (DO NOT include options field)
  * correctAnswer: { "min": 3.14, "max": 3.14 } (use same value for exact answer)

--------------------------------------------------
FAIL-SAFE RULES:
- If an image-only question exists -> still create a question entry.
- If question type is unclear -> default to "single".
- If answer key exists separately -> map carefully to question IDs.
- If ANY field is missing -> set it to null (never omit keys).
- If correctAnswer cannot be determined, set it to null.
- If diagram extraction fails, set diagramPage to null but keep the question.

--------------------------------------------------
FINAL OUTPUT RULE:
RETURN ONLY RAW JSON.
NO TEXT BEFORE OR AFTER.
"""

ANSWER_KEY_PROMPT = """
You are analyzing an ANSWER KEY document/image. Your task is to extract the correct answers and map them to question numbers.

Extract the answer key in this format:
{
  "answer_key": [
    {"question_number": 1, "answer": "A"},
    {"question_number": 2, "answer": ["A", "C"]},
    {"question_number": 3, "answer": "3.14"},
    ...
  ]
}

Rules:
- For single choice: answer is a single letter like "A", "B", "C", or "D"
- For multiple choice: answer is an array of letters like ["A", "C"]
- For numerical: answer is the number as a string like "3.14" or "42"
- Match question numbers exactly as shown in the answer key
- If question numbers are not shown, assume they are in order starting from 1
- Common formats to detect: "1. A", "Q1: B", "Answer 1: C", "1 - D"

Return ONLY valid JSON. No markdown, no explanations.
"""

GENERATE_PROMPT = """
You are an expert educator and exam setter. You will receive images of document pages (textbook, notes, exam paper, etc.).

## YOUR TASK
Analyze the content thoroughly and **generate new, original MCQ questions** based on the topics and concepts covered.

## RULES
1. **Generate as many questions as reasonable** (minimum 10, aim for 15-25 depending on content density).
2. **Questions must be original** — do not copy questions verbatim if they exist in the document.
3. **Cover all topics** in the document proportionally.
4. **Vary difficulty**: mix easy, medium, and hard questions.
5. **CRITICAL - Mathematical content**: Write math in PLAIN TEXT using Unicode symbols.
   - Use ^ for superscripts: x^2, e^(ikx)
   - Use / for fractions: 1/2, a/b
   - Use sqrt() for roots: sqrt(3)
   - Use Unicode: π, θ, α, β, ω, Σ, ∫, ∞, ≥, ≤, ≠, ±, ×, →
   - Do NOT use LaTeX backslash commands.
6. **All questions must have exactly one correct answer** specified.
7. **Create plausible distractors** — wrong options should be reasonable, not obviously wrong.

## CROSS-PAGE HANDLING:
- Questions may span multiple pages - combine them into complete questions
- Never split a single question into multiple entries

## OUTPUT FORMAT
Return ONLY valid JSON (no markdown fences, no explanation):
{
  "title": "Generated: [Topic/Subject]",
  "description": "AI-generated questions based on [content summary]",
  "revision_notes": "# Key Concepts\\n* Point 1\\n* Point 2\\n...",
  "questions": [
    {
      "id": 1,
      "type": "single",
      "question": "Original question text here",
      "options": { "A": "Option A", "B": "Option B", "C": "Option C", "D": "Option D" },
      "correctAnswer": "C",
      "marks": 1,
      "negativeMarks": 0,
      "crossPage": false
    }
  ]
}
"""


# ---------------------------------------------------------------------------
# Core Pipeline
# ---------------------------------------------------------------------------

def render_pages_as_images(pdf_bytes: bytes, dpi: int = 300) -> List[bytes]:
    """Render each PDF page as a PNG image at the specified DPI."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page_images = []

    zoom = dpi / 72  # 72 is the default DPI
    mat = fitz.Matrix(zoom, zoom)

    for page_num in range(len(doc)):
        page = doc[page_num]
        pix = page.get_pixmap(matrix=mat, alpha=False)

        img_bytes = pix.tobytes("png")
        page_images.append(img_bytes)
        logger.debug(f"Rendered page {page_num + 1}: {pix.width}x{pix.height} ({len(img_bytes)} bytes)")

    doc.close()
    logger.info(f"Rendered {len(page_images)} pages as images at {dpi} DPI")
    return page_images


def extract_embedded_images(pdf_bytes: bytes) -> List[Dict]:
    """
    Extract ALL embedded images from the PDF.
    Keeps diagrams of all sizes - even small chemical structures are important.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    images = []
    seen_hashes = set()

    for page_num in range(len(doc)):
        page = doc[page_num]
        image_list = page.get_images(full=True)

        for img_info in image_list:
            xref = img_info[0]
            try:
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                ext = base_image["ext"]

                # Deduplicate by content hash
                img_hash = hash(image_bytes)
                if img_hash in seen_hashes:
                    continue
                seen_hashes.add(img_hash)

                # Extract ALL images regardless of size
                # Small diagrams (chemical structures, symbols) are important
                w = base_image["width"]
                h = base_image["height"]
                
                # Only filter out extremely tiny icons (less than 20x20)
                if w < 20 or h < 20:
                    continue

                # Get position on page
                rects = page.get_image_rects(xref)
                bbox = None
                if rects:
                    rect = rects[0]
                    bbox = (rect.x0, rect.y0, rect.x1, rect.y1)

                images.append({
                    "page": page_num + 1,
                    "data": base64.b64encode(image_bytes).decode("utf-8"),
                    "ext": ext,
                    "width": w,
                    "height": h,
                    "bbox": bbox,
                    "base64_uri": f"data:image/{ext};base64,{base64.b64encode(image_bytes).decode('utf-8')}"
                })
            except Exception as e:
                logger.warning(f"Failed to extract image from page {page_num + 1}: {e}")

    doc.close()
    logger.info(f"Extracted {len(images)} images from PDF")
    return images


def convert_image_to_bytes(image_bytes: bytes, target_format: str = "png") -> bytes:
    """Convert any image format to standardized bytes."""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        # Convert to RGB if necessary (for PNG compatibility)
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        
        output = io.BytesIO()
        img.save(output, format=target_format.upper())
        return output.getvalue()
    except Exception as e:
        logger.warning(f"Failed to convert image: {e}, returning original")
        return image_bytes


def is_pdf(file_bytes: bytes) -> bool:
    """Check if the file bytes represent a PDF."""
    return file_bytes.startswith(b'%PDF')


def is_image(filename: str) -> bool:
    """Check if the filename represents an image."""
    ext = filename.lower()
    return any(ext.endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp'])


def normalize_question_id(q_id) -> int:
    """
    Normalize question ID to integer for matching.
    Handles formats like: 1, "1", "Q1", "Question 1", "1.", etc.
    """
    if isinstance(q_id, int):
        return q_id
    
    if isinstance(q_id, str):
        # Remove common prefixes and suffixes
        cleaned = q_id.strip()
        cleaned = re.sub(r'^(Q|Question|No|#)\s*', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'[.:)\]]\s*$', '', cleaned)
        cleaned = cleaned.strip()
        
        try:
            return int(cleaned)
        except ValueError:
            # If can't convert, return original as string
            logger.warning(f"Could not normalize question ID: {q_id}")
            return q_id
    
    return q_id


async def process_answer_key(answer_key_data: Dict) -> List[Dict]:
    """
    Process an answer key file (PDF or image) and extract answer mappings.
    Returns a list of {question_number, answer} dictionaries.
    """
    if not api_key:
        logger.warning("No Gemini API key configured, skipping answer key processing")
        return []
    
    logger.info("Processing answer key...")
    
    # Convert answer key to images
    images = []
    if is_pdf(answer_key_data["content"]):
        images = render_pages_as_images(answer_key_data["content"], dpi=300)
    elif is_image(answer_key_data["filename"]):
        images = [convert_image_to_bytes(answer_key_data["content"])]
    else:
        logger.warning("Unknown answer key format, treating as image")
        images = [answer_key_data["content"]]
    
    if not images:
        logger.warning("No images extracted from answer key")
        return []
    
    # Send to Gemini for answer extraction
    content_parts = [ANSWER_KEY_PROMPT]
    for i, img_bytes in enumerate(images):
        content_parts.append(f"\n--- ANSWER KEY PAGE {i + 1} ---\n")
        content_parts.append({
            "mime_type": "image/png",
            "data": base64.b64encode(img_bytes).decode("utf-8")
        })
    
    try:
        model = genai.GenerativeModel(
            model_name="gemini-2.0-flash",
            generation_config={
                "temperature": 0.1,
                "top_p": 0.95,
                "max_output_tokens": 4096,
            }
        )
        
        response = model.generate_content(content_parts)
        raw_text = response.text
        
        # Parse the answer key JSON
        clean = raw_text.strip()
        if clean.startswith("```json"):
            clean = clean[7:]
        elif clean.startswith("```"):
            clean = clean[3:]
        if clean.endswith("```"):
            clean = clean[:-3]
        clean = clean.strip()
        
        data = json.loads(clean)
        answer_key = data.get("answer_key", [])
        
        logger.info(f"Extracted {len(answer_key)} answers from answer key")
        return answer_key
        
    except Exception as e:
        logger.error(f"Error processing answer key: {e}")
        return []


async def process_pdf(file_bytes: bytes, mode: str = "extract") -> Dict:
    """
    Legacy function for backward compatibility.
    Processes a single PDF file.
    """
    file_data = [{
        "filename": "document.pdf",
        "content": file_bytes,
        "content_type": "application/pdf"
    }]
    return await process_files(file_data, mode=mode, answer_key=None)


def merge_cross_page_questions(all_questions: List[Dict]) -> List[Dict]:
    """
    Merge questions that span across multiple pages.
    Groups questions by normalized ID and combines their content.
    """
    # Group questions by normalized ID
    question_groups: Dict[int, List[Dict]] = {}
    
    for q in all_questions:
        q_id = normalize_question_id(q.get("id"))
        if q_id not in question_groups:
            question_groups[q_id] = []
        question_groups[q_id].append(q)
    
    # Merge questions with same ID
    merged_questions = []
    for q_id, group in question_groups.items():
        if len(group) == 1:
            # No merging needed
            merged_questions.append(group[0])
        else:
            # Merge multiple parts of the same question
            logger.info(f"Merging {len(group)} parts of question {q_id}")
            merged = merge_question_parts(group)
            merged_questions.append(merged)
    
    # Sort by ID
    merged_questions.sort(key=lambda x: normalize_question_id(x.get("id")))
    
    return merged_questions


def merge_question_parts(parts: List[Dict]) -> Dict:
    """
    Merge multiple parts of the same question into one complete question.
    """
    # Start with the first part
    merged = parts[0].copy()
    
    # Collect all text parts
    all_question_texts = []
    all_options = {}
    diagram_pages = []
    
    for part in parts:
        # Collect question text if not empty
        q_text = part.get("question", "")
        if q_text and q_text.strip():
            all_question_texts.append(q_text.strip())
        
        # Collect options
        opts = part.get("options", {})
        if opts:
            for key, value in opts.items():
                if value and value.strip():
                    all_options[key] = value
        
        # Track diagram pages
        if part.get("diagramPage"):
            diagram_pages.append(part["diagramPage"])
        
        # Keep the correct answer if found
        if part.get("correctAnswer") and not merged.get("correctAnswer"):
            merged["correctAnswer"] = part["correctAnswer"]
        
        # Keep the type if more specific
        if part.get("type") and part["type"] != "single":
            merged["type"] = part["type"]
    
    # Merge question texts (remove duplicates, preserve order)
    seen_texts = set()
    unique_texts = []
    for text in all_question_texts:
        # Simple deduplication - check if text is substring of already seen
        is_duplicate = False
        for seen in seen_texts:
            if text in seen or seen in text:
                is_duplicate = True
                break
        if not is_duplicate:
            seen_texts.add(text)
            unique_texts.append(text)
    
    merged["question"] = " <br><br> ".join(unique_texts)
    
    # Merge options
    if all_options:
        merged["options"] = all_options
        # Update optionImages to match
        merged["optionImages"] = {k: None for k in all_options.keys()}
    
    # Use first diagram page
    if diagram_pages:
        merged["diagramPage"] = min(diagram_pages)
    
    # Mark as cross-page
    merged["crossPage"] = True
    
    return merged


async def process_files(file_data: List[Dict], mode: str = "extract", answer_key: Optional[Dict] = None) -> Dict:
    """
    Main pipeline entry point for processing multiple files (PDFs and/or images).
    
    Strategy:
    1. Convert all files to page images at HIGH QUALITY (300 DPI)
    2. If answer key provided, extract answers first
    3. Send page images to Gemini Vision for question extraction
    4. Match extracted answers with questions if answer key was provided
    5. Separately extract embedded images for diagram matching
    6. Merge questions that span across pages
    """
    if not api_key:
        raise ValueError("Gemini API key not configured. Set GEMINI_API_KEY environment variable.")

    logger.info(f"Starting Vision Pipeline in '{mode}' mode with {len(file_data)} file(s)...")

    # Step 1: Process answer key if provided
    answer_key_mappings = []
    if answer_key:
        answer_key_mappings = await process_answer_key(answer_key)
        logger.info(f"Answer key loaded with {len(answer_key_mappings)} mappings")

    # Step 2: Convert all files to page images at HIGH QUALITY
    logger.info("Converting files to high-quality images (300 DPI)...")
    all_page_images = []
    all_embedded_images = []
    
    for file_info in file_data:
        filename = file_info["filename"]
        content = file_info["content"]
        
        if is_pdf(content):
            logger.info(f"Processing PDF: {filename}")
            pdf_pages = render_pages_as_images(content, dpi=300)  # HIGH QUALITY
            all_page_images.extend(pdf_pages)
            
            # Extract ALL embedded images from PDF (minimal filtering)
            embedded = extract_embedded_images(content)
            all_embedded_images.extend(embedded)
            
        elif is_image(filename):
            logger.info(f"Processing Image: {filename}")
            img_bytes = convert_image_to_bytes(content)
            all_page_images.append(img_bytes)
        else:
            logger.warning(f"Unknown file type: {filename}, attempting to process as image")
            all_page_images.append(content)

    if not all_page_images:
        raise ValueError("No pages/images could be extracted from the provided files")

    logger.info(f"Total pages/images to process: {len(all_page_images)}")

    # Step 3: Process pages with overlap for cross-page questions
    MAX_PAGES_PER_BATCH = 5
    OVERLAP_PAGES = 1  # Include last page of previous batch in next batch
    prompt = EXTRACT_PROMPT if mode == "extract" else GENERATE_PROMPT
    all_questions = []
    
    total_pages = len(all_page_images)
    start_idx = 0
    batch_num = 0
    
    while start_idx < total_pages:
        batch_num += 1
        end_idx = min(start_idx + MAX_PAGES_PER_BATCH, total_pages)
        
        # Get batch images with overlap from previous batch
        if start_idx == 0:
            batch_images = all_page_images[start_idx:end_idx]
            batch_start_page = start_idx
        else:
            # Include overlap page from previous batch
            batch_images = all_page_images[start_idx - OVERLAP_PAGES:end_idx]
            batch_start_page = start_idx - OVERLAP_PAGES
        
        actual_batch_size = len(batch_images)
        logger.info(f"Processing batch {batch_num}: Pages {batch_start_page + 1}-{batch_start_page + actual_batch_size}")

        content_parts = [prompt]
        
        for i, page_img in enumerate(batch_images):
            actual_page_num = batch_start_page + i + 1
            content_parts.append(f"\n--- PAGE {actual_page_num} of {total_pages} ---\n")
            content_parts.append({
                "mime_type": "image/png",
                "data": base64.b64encode(page_img).decode("utf-8")
            })

        logger.info(f"Sending batch {batch_num} to Gemini...")
        
        try:
            model = genai.GenerativeModel(
                model_name="gemini-2.0-flash",
                generation_config={
                    "temperature": 0.1,
                    "top_p": 0.95,
                    "max_output_tokens": 65536,
                }
            )
            response = model.generate_content(content_parts)
            raw_text = response.text
            
            logger.info(f"Batch {batch_num} response received. Length: {len(raw_text)}")
            
            batch_result = _parse_response(raw_text, all_embedded_images)
            questions = batch_result.get("questions", [])
            
            if questions:
                logger.info(f"Extracted {len(questions)} questions from batch {batch_num}")
                all_questions.extend(questions)
            
        except Exception as e:
            logger.error(f"Error processing batch {batch_num}: {e}")
            # Continue to next batch instead of failing entire document
        
        # Move to next batch
        start_idx = end_idx

    if not all_questions:
        raise ValueError("No questions could be extracted from any batch.")

    logger.info(f"Total questions extracted before merging: {len(all_questions)}")

    # Step 4: Merge cross-page questions
    logger.info("Merging cross-page questions...")
    unique_questions = merge_cross_page_questions(all_questions)
    logger.info(f"Total questions after merging: {len(unique_questions)}")

    # Step 5: Match answer key with questions if provided (PRIORITY)
    if answer_key_mappings:
        logger.info("Matching separate answer key with extracted questions...")
        unique_questions = _match_answer_key(unique_questions, answer_key_mappings)
    else:
        # If no separate answer key, check if inline answers were detected
        logger.info("No separate answer key provided - relying on inline answer detection")

    result = {
        "title": "Extracted Exam",
        "description": f"Extracted from {total_pages} pages",
        "questions": unique_questions,
        "canConfirm": all(q.get("correctAnswer") is not None for q in unique_questions),
        "unansweredCount": sum(1 for q in unique_questions if q.get("correctAnswer") is None),
    }

    return result


def _match_answer_key(questions: List[Dict], answer_key: List[Dict]) -> List[Dict]:
    """
    Match extracted questions with answer key mappings.
    Updates correctAnswer field based on answer key.
    Uses normalized question IDs for flexible matching.
    """
    # Create a lookup from normalized question number to answer
    answer_lookup: Dict[int, any] = {}
    for mapping in answer_key:
        q_num = mapping.get("question_number")
        answer = mapping.get("answer")
        if q_num is not None and answer is not None:
            normalized_num = normalize_question_id(q_num)
            answer_lookup[normalized_num] = answer
            logger.debug(f"Answer key mapping: Q{normalized_num} -> {answer}")
    
    logger.info(f"Answer key contains {len(answer_lookup)} normalized mappings")
    
    # Update questions with correct answers
    matched_count = 0
    unmatched_questions = []
    
    for q in questions:
        q_id = q.get("id")
        normalized_q_id = normalize_question_id(q_id)
        
        logger.debug(f"Trying to match question {q_id} (normalized: {normalized_q_id})")
        
        if normalized_q_id in answer_lookup:
            answer = answer_lookup[normalized_q_id]
            
            # Handle different answer formats
            if isinstance(answer, list):
                # Multiple choice
                q["correctAnswer"] = answer
                q["type"] = "multiple"
                logger.debug(f"Matched Q{normalized_q_id} as multiple choice: {answer}")
            elif isinstance(answer, str):
                if answer.upper() in ['A', 'B', 'C', 'D', 'E']:
                    # Single choice
                    q["correctAnswer"] = answer.upper()
                    logger.debug(f"Matched Q{normalized_q_id} as single choice: {answer.upper()}")
                else:
                    # Try to parse as numerical
                    try:
                        num_val = float(answer)
                        q["correctAnswer"] = {"min": num_val, "max": num_val}
                        q["type"] = "numerical"
                        logger.debug(f"Matched Q{normalized_q_id} as numerical: {num_val}")
                    except:
                        # Keep as string
                        q["correctAnswer"] = answer
                        logger.debug(f"Matched Q{normalized_q_id} as string: {answer}")
            
            matched_count += 1
        else:
            unmatched_questions.append(q_id)
    
    logger.info(f"Successfully matched {matched_count}/{len(questions)} questions with answer key")
    if unmatched_questions:
        logger.info(f"Unmatched questions: {unmatched_questions}")
    
    return questions


# ---------------------------------------------------------------------------
# JSON Sanitization
# ---------------------------------------------------------------------------

def _sanitize_gemini_json(text: str) -> str:
    """
    Fix common JSON issues in Gemini responses:
    1. LaTeX backslash commands that break JSON parsing
    2. Unquoted values
    3. Truncated output — try to close incomplete JSON
    """
    # Fix 1: Quote unquoted IMG references if any
    text = re.sub(r':\s*(IMG_\d+)\s*([,}\]])', r': "\1"\2', text)

    # Fix 2: Handle LaTeX backslashes.
    # Gemini should double-escape (\\frac), but sometimes uses single (\frac).
    # Strategy: any \<letters> where letters form 2+ chars → escape the backslash
    def fix_backslash(match):
        word = match.group(1)
        if len(word) >= 2:
            return '\\\\' + word
        elif word in 'bfnrtu':
            return '\\' + word
        else:
            return '\\\\' + word

    text = re.sub(r'(?<!\\)\\([a-zA-Z]+)', fix_backslash, text)

    # Fix 3: Handle \( and \) LaTeX delimiters
    text = text.replace('\\(', '(').replace('\\)', ')')

    # Fix 4: Handle truncated JSON — try to close it
    text = text.rstrip()
    if not text.endswith('}'):
        # Try to find the last complete question and close the JSON
        logger.warning("Detected potentially truncated JSON response, attempting to repair...")
        text = _repair_truncated_json(text)

    return text


def _repair_truncated_json(text: str) -> str:
    """
    Attempt to repair truncated JSON by closing open structures.
    Works by finding the last complete question object and closing the array/object.
    """
    # Find the last complete question object (ends with })
    # Look for the pattern: }, followed by possible whitespace, then either , or ]
    last_complete = text.rfind('"negativeMarks"')
    if last_complete == -1:
        last_complete = text.rfind('"marks"')
    if last_complete == -1:
        last_complete = text.rfind('"correctAnswer"')

    if last_complete > 0:
        # Find the closing } of this question object after the last key
        close_pos = text.find('}', last_complete)
        if close_pos > 0:
            # Keep everything up to and including this }
            text = text[:close_pos + 1]
            # Close the questions array and outer object
            text += '\n  ]\n}'
            logger.info(f"Repaired truncated JSON (cut at position {close_pos + 1})")
    else:
        # Can't find a good cut point, try brute force closing
        # Count open/close braces and brackets
        open_braces = text.count('{') - text.count('}')
        open_brackets = text.count('[') - text.count(']')

        # Find and remove the last incomplete string
        last_quote = text.rfind('"')
        if last_quote > 0:
            # Check if string is unterminated
            preceding = text[:last_quote]
            if preceding.count('"') % 2 == 0:
                # This quote opens a new string that's unterminated
                text = text[:last_quote] + '"null"'

        # Close remaining open structures
        text += ']' * max(0, open_brackets)
        text += '}' * max(0, open_braces)

    return text


def _parse_response(raw_text: str, embedded_images: List[Dict]) -> Dict:
    """Parse Gemini's JSON response and match diagrams to questions."""
    # Clean markdown code fences if present
    clean = raw_text.strip()
    if clean.startswith("```json"):
        clean = clean[7:]
    elif clean.startswith("```"):
        clean = clean[3:]
    if clean.endswith("```"):
        clean = clean[:-3]
    clean = clean.strip()

    # Try parsing raw first, then sanitize if needed
    try:
        data = json.loads(clean)
    except json.JSONDecodeError:
        logger.info("Raw JSON parse failed, applying sanitization...")
        sanitized = _sanitize_gemini_json(clean)
        try:
            data = json.loads(sanitized)
            logger.info("Sanitized JSON parsed successfully")
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error after sanitization: {e}")
            logger.error(f"Raw text (first 2000 chars): {clean[:2000]}")
            raise ValueError(f"AI returned invalid JSON: {e}")

    questions = data.get("questions", [])
    if not questions:
        raise ValueError("AI returned 0 questions. The document may not contain extractable content.")

    # Build page → images lookup for diagram matching
    page_images_map = {}
    for img in embedded_images:
        page = img["page"]
        if page not in page_images_map:
            page_images_map[page] = []
        page_images_map[page].append(img)

    # Validate and match diagrams
    validated = []
    for i, q in enumerate(questions):
        if not isinstance(q, dict):
            continue

        question_text = q.get("question") or q.get("questionText") or ""
        if not question_text:
            logger.warning(f"Question {i + 1} has no text, skipping")
            continue

        # Match diagram by page number
        q_image = q.get("image")
        diagram_page = q.get("diagramPage")
        diagram_option = q.get("diagramOption")  # New field for option-specific diagrams

        # If image is already a data URI or URL, keep it
        if q_image and isinstance(q_image, str) and (q_image.startswith("data:") or q_image.startswith("http")):
            pass  # keep as-is
        elif diagram_page and diagram_page in page_images_map:
            # Get images from that page
            page_imgs = page_images_map[diagram_page]
            if page_imgs:
                # If diagramOption is specified, try to find image near that option
                if diagram_option:
                    # For now, use position-based selection (could be enhanced with OCR)
                    best = page_imgs[0]  # Use first image as fallback
                else:
                    # Pick the most relevant image (considering size but not filtering small ones)
                    # Sort by size but don't exclude small ones
                    sorted_imgs = sorted(page_imgs, key=lambda x: x["width"] * x["height"], reverse=True)
                    # Use the largest as default, but small diagrams are still available
                    best = sorted_imgs[0] if sorted_imgs else None
                
                if best:
                    q_image = best["base64_uri"]
        else:
            q_image = None

        # Ensure options exist (not for numerical type)
        options = q.get("options", {})
        q_type = q.get("type", "single")
        if not options and q_type != "numerical":
            options = {"A": "", "B": "", "C": "", "D": ""}

        validated.append({
            "id": q.get("id", i + 1),
            "type": q_type,
            "question": question_text,
            "image": q_image,
            "options": options,
            "optionImages": {k: None for k in options.keys()} if options else {},
            "correctAnswer": q.get("correctAnswer"),
            "marks": q.get("marks", 4),
            "negativeMarks": q.get("negativeMarks", 1),
            "crossPage": q.get("crossPage", False),
        })

    result = {
        "title": data.get("title", ""),
        "description": data.get("description", ""),
        "questions": validated,
        "canConfirm": all(q.get("correctAnswer") is not None for q in validated),
        "unansweredCount": sum(1 for q in validated if q.get("correctAnswer") is None),
    }

    # Include revision notes for generate mode
    if data.get("revision_notes"):
        result["revision_notes"] = data.get("revision_notes")

    return result
