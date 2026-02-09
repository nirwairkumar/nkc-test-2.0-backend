import os
import json
import google.generativeai as genai
from utils.logger import get_logger
from ai_preview_importer.prompts import MASTER_PROMPT

logger = get_logger(__name__)

# Configure Gemini
api_key = os.environ.get("VITE_GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
if not api_key:
    logger.warning("VITE_GEMINI_API_KEY not found in environment variables.")
else:
    genai.configure(api_key=api_key)

generation_config = {
  "temperature": 0.1,
  "top_p": 0.95,
  "top_k": 40,
  "max_output_tokens": 8192,
}

async def analyze_page_refinement(raw_blocks, images, candidates, page_num):
    """
    Sends raw content to Gemini for FULL Exam Reconstruction.
    Input: Raw text blocks, images, and optional candidates.
    Output: List of RECONSTRUCTED questions (JSON).
    """
    try:
        if not api_key:
             raise ValueError("API Key missing. Cannot run AI analysis.")

        model = genai.GenerativeModel(
            model_name="gemini-3.0-pro-preview", 
            generation_config=generation_config
        )

        # Prepare Input Data according to PROMPT requirements
        input_data = {
            "page_number": page_num,
            "raw_text_blocks": raw_blocks,
            "image_metadata": [{"id": f"IMG_{i}", "bbox": img.get('bbox')} for i, img in enumerate(images)],
            "candidates_from_regex": candidates
        }

        # Combine System Prompt with User Prompt for compatibility with older SDKs
        user_content = f"""
{MASTER_PROMPT}

--------------------------------------------------

Reconstruct the exam from the following raw data:
{json.dumps(input_data, indent=2)}
"""

        logger.info(f"Sending Page {page_num} (Refinement) to AI...")
        response = model.generate_content(user_content)
        
        try:
            raw_text = response.text
        except Exception:
            logger.warning(f"AI blocked response for Page {page_num}. Safety reasons likely.")
            return []

        logger.info(f"AI Response received for Page {page_num}. Length: {len(raw_text)}")
        
        # DEBUG: Log the first 500 chars to see what's happening if it fails
        logger.debug(f"Raw AI Output (Snippet): {raw_text[:500]}...")

        # Clean Markdown wrappers
        clean_text = raw_text.strip()
        if clean_text.startswith("```json"):
            clean_text = clean_text[7:]
        elif clean_text.startswith("```"):
            clean_text = clean_text[3:]
        if clean_text.endswith("```"):
            clean_text = clean_text[:-3]
        clean_text = clean_text.strip()

        # Parse Response
        try:
            result_json = json.loads(clean_text)
        except json.JSONDecodeError:
            logger.error(f"JSON Parse Error on Page {page_num}. Dumping raw text for debugging.")
            logger.error(raw_text) # Dump full text
            return []
        
        refined_questions = result_json.get("questions", [])
        
        # Log success details
        logger.info(f"Successfully extracted {len(refined_questions)} questions from JSON for Page {page_num}")
        
        return refined_questions

    except Exception as e:
        logger.error(f"AI Analysis failed for Page {page_num}: {str(e)}")
        # If we have the raw text, log it
        if 'raw_text' in locals():
             logger.error(f"Failed Content: {raw_text}")
        return []
