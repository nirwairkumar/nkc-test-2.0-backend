"""
PDF Vision Pipeline - Full-page vision approach using Gemini
Replaces the fragmented text-block + spatial-analysis pipeline with a simple,
accurate approach: render pages as images → send to Gemini Vision → parse results.

Supports two modes:
  - "extract": Extract exact questions from the exam paper as-is
  - "generate": Create new original MCQs based on the PDF content
"""
import os
import io
import re
import json
import base64
import fitz  # PyMuPDF
import google.generativeai as genai
from typing import Dict, List, Optional
from utils.logger import get_logger
from app.core.config import settings

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
Convert the PROVIDED PDF pages into a STRICT, VALID JSON test file.
DO NOT generate new questions.
ONLY extract and restructure content that exists in the file.

CRITICAL BEHAVIOR RULES:
- Read the uploaded pages visually (OCR + layout reasoning).
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
DOCUMENT ANALYSIS STEPS (MANDATORY):
1. Detect each question boundary using:
   - Question numbers
   - Line breaks
   - Bullets (Q., 1., 1), etc.)
2. For each question:
   - Extract full question text
   - DETECT TYPE based on indicators above
   - Extract options (A/B/C/D) ONLY for single/multiple choice
3. Detect correct answers using:
   - Answer keys
   - Highlighted/marked answers
   - End-of-page answer sections
4. Convert all mathematical expressions into LaTeX.
5. Preserve original wording (do NOT rewrite).
6. If a question has a diagram/figure on the page, set "diagramPage" to that page number.
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
      "options": {
        "A": "Option text",
        "B": "Option text",
        "C": "Option text",
        "D": "Option text"
      },
      "correctAnswer": "A",
      "marks": 4,
      "negativeMarks": 1
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

--------------------------------------------------
FINAL OUTPUT RULE:
RETURN ONLY RAW JSON.
NO TEXT BEFORE OR AFTER.
"""

GENERATE_PROMPT = """
You are an expert educator and exam setter. You will receive images of every page of a PDF document (textbook, notes, exam paper, etc.).

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
      "negativeMarks": 0
    }
  ]
}
"""


# ---------------------------------------------------------------------------
# Core Pipeline
# ---------------------------------------------------------------------------

def render_pages_as_images(pdf_bytes: bytes, dpi: int = 200) -> List[bytes]:
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
    Extract meaningful embedded images (diagrams, figures) from the PDF.
    Filters out icons, logos, watermarks, and tiny images.
    Images are grouped by page for later matching with questions.
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

                # Filter: skip small/irrelevant images
                w = base_image["width"]
                h = base_image["height"]
                if w < 100 or h < 100:
                    continue
                if w * h < 15000:
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
    logger.info(f"Extracted {len(images)} meaningful embedded images")
    return images


async def process_pdf(file_bytes: bytes, mode: str = "extract") -> Dict:
    """
    Main pipeline entry point.
    
    Strategy:
    1. Render pages as images → send ONLY page images to Gemini
    2. Gemini sees the full visual layout and extracts questions
    3. Separately extract embedded images for diagram matching
    4. Match diagrams to questions by page number
    """
    if not api_key:
        raise ValueError("Gemini API key not configured. Set GEMINI_API_KEY environment variable.")

    logger.info(f"Starting PDF Vision Pipeline in '{mode}' mode...")

    # Step 1: Render pages as images
    logger.info("Step 1: Rendering PDF pages as images...")
    page_images = render_pages_as_images(file_bytes, dpi=200)

    if not page_images:
        raise ValueError("PDF has no pages or could not be rendered")

    # Step 2: Extract embedded images (for diagram matching later, NOT sent to Gemini)
    logger.info("Step 2: Extracting embedded images for diagram matching...")
    embedded_images = extract_embedded_images(file_bytes)

    MAX_PAGES_PER_BATCH = 5
    prompt = EXTRACT_PROMPT if mode == "extract" else GENERATE_PROMPT
    all_questions = []

    # Process in batches to avoid token limits
    total_pages = len(page_images)
    for start_idx in range(0, total_pages, MAX_PAGES_PER_BATCH):
        end_idx = min(start_idx + MAX_PAGES_PER_BATCH, total_pages)
        batch_images = page_images[start_idx:end_idx]
        
        logger.info(f"Processing batch {start_idx//MAX_PAGES_PER_BATCH + 1}: Pages {start_idx + 1}-{end_idx}")

        content_parts = [prompt]
        
        for i, page_img in enumerate(batch_images):
            # Page numbers in prompt should be 1-based relative to the document
            content_parts.append(f"\n--- PAGE {start_idx + i + 1} of {total_pages} ---\n")
            content_parts.append({
                "mime_type": "image/png",
                "data": base64.b64encode(page_img).decode("utf-8")
            })

        logger.info(f"Sending batch {start_idx//MAX_PAGES_PER_BATCH + 1} to Gemini...")
        
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
            
            logger.info(f"Batch {start_idx//MAX_PAGES_PER_BATCH + 1} response received. Length: {len(raw_text)}")
            
            batch_result = _parse_response(raw_text, embedded_images)
            questions = batch_result.get("questions", [])
            
            if questions:
                # Adjust IDs to be sequential across batches if needed, 
                # but usually we trust the doc's numbering. 
                # If duplicates exist, we might need to re-number.
                all_questions.extend(questions)
                logger.info(f"Extracted {len(questions)} questions from batch")
            
        except Exception as e:
            logger.error(f"Error processing batch {start_idx}-{end_idx}: {e}")
            # Continue to next batch instead of failing entire document
            continue

    if not all_questions:
        raise ValueError("No questions could be extracted from any batch.")

    # Deduplicate by ID just in case
    # (Sometimes previous batch context leaks or page overlap causes dupes)
    unique_questions = []
    seen_ids = set()
    for q in all_questions:
        if q["id"] not in seen_ids:
            unique_questions.append(q)
            seen_ids.add(q["id"])
    
    # Sort by ID
    unique_questions.sort(key=lambda x: int(x["id"]) if isinstance(x["id"], int) or x["id"].isdigit() else 9999)

    result = {
        "title": "Extracted Exam",  # simplified
        "description": f"Extracted from {total_pages} pages",
        "questions": unique_questions,
        "canConfirm": all(q.get("correctAnswer") is not None for q in unique_questions),
        "unansweredCount": sum(1 for q in unique_questions if q.get("correctAnswer") is None),
    }

    return result


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
        raise ValueError("AI returned 0 questions. The PDF may not contain extractable content.")

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

        # If image is already a data URI or URL, keep it
        if q_image and isinstance(q_image, str) and (q_image.startswith("data:") or q_image.startswith("http")):
            pass  # keep as-is
        elif diagram_page and diagram_page in page_images_map:
            # Pick the largest relevant image from that page
            page_imgs = page_images_map[diagram_page]
            if page_imgs:
                best = max(page_imgs, key=lambda x: x["width"] * x["height"])
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
        result["revision_notes"] = data["revision_notes"]

    return result
