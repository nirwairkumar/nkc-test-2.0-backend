"""
AI Reasoner V2 - Enhanced analysis with Gemini Vision API
Uses Gemini API for all AI processing
"""
import os
import json
import base64
import google.generativeai as genai
from typing import List, Dict
from utils.logger import get_logger
from ai_preview_importer.prompts_v2 import (
    MASTER_PROMPT_V2,
    VISION_ANALYSIS_PROMPT,
    QUESTION_RECONSTRUCTION_PROMPT
)

logger = get_logger(__name__)

# Configure Gemini
api_key = os.environ.get("VITE_GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
if not api_key:
    logger.warning("Gemini API key not found in environment variables")
else:
    genai.configure(api_key=api_key)

generation_config = {
    "temperature": 0.1,
    "top_p": 0.95,
    "top_k": 40,
    "max_output_tokens": 8192,
}


async def analyze_with_vision_and_text(
    text_blocks: List[Dict],
    images: List[Dict],
    spatial_relationships: List[Dict],
    page_num: int,
    page_layout: Dict
) -> List[Dict]:
    """
    Enhanced analysis using Gemini Vision API.
    
    Process:
    1. Send page image to Vision API for visual analysis
    2. Combine visual analysis with extracted text
    3. Use spatial relationships to accurately reconstruct questions
    
    Returns: List of reconstructed question objects
    """
    try:
        if not api_key:
            raise ValueError("Gemini API key missing. Cannot run AI analysis")
        
        # Use Gemini 2.0 Flash for vision + text analysis
        model = genai.GenerativeModel(
            model_name="gemini-2.0-flash-exp",
            generation_config=generation_config
        )
        
        # Prepare structured input
        input_data = {
            "page_number": page_num,
            "layout": {
                "num_columns": page_layout.get('num_columns', 1),
                "page_width": page_layout.get('page_width'),
                "page_height": page_layout.get('page_height')
            },
            "text_blocks": [
                {
                    "text": block['text'],
                    "bbox": block['bbox'],
                    "font_size": block.get('font_size', 12),
                    "is_bold": block.get('is_bold', False),
                    "reading_order": block.get('reading_order', 0)
                }
                for block in text_blocks
            ],
            "images": [
                {
                    "id": img['id'],
                    "bbox": img['bbox'],
                    "type": img.get('type', 'unknown'),
                    "width": img.get('width'),
                    "height": img.get('height')
                }
                for img in images
            ],
            "spatial_relationships": spatial_relationships
        }
        
        # Prepare content for Gemini
        content_parts = []
        
        # Add the master prompt
        content_parts.append(MASTER_PROMPT_V2)
        
        # Add images for visual analysis
        for img in images:
            try:
                # Extract base64 data
                base64_data = img['base64'].split(',')[1] if ',' in img['base64'] else img['base64']
                
                # Add image to content
                content_parts.append({
                    'mime_type': 'image/png',
                    'data': base64_data
                })
                
                content_parts.append(f"\n[Image ID: {img['id']}, Type: {img.get('type', 'unknown')}]\n")
            except Exception as e:
                logger.warning(f"Failed to add image {img.get('id')} to vision analysis: {e}")
        
        # Add the structured data
        content_parts.append(f"\n\n## EXTRACTED DATA\n\n{json.dumps(input_data, indent=2)}")
        
        # Add reconstruction instruction
        content_parts.append(f"\n\n{QUESTION_RECONSTRUCTION_PROMPT}")
        
        logger.info(f"Sending Page {page_num} to Gemini Vision API...")
        
        # Generate content with vision + text
        response = model.generate_content(content_parts)
        
        try:
            raw_text = response.text
        except Exception as e:
            logger.warning(f"Gemini blocked response for Page {page_num}: {e}")
            return []
        
        logger.info(f"Gemini response received for Page {page_num}. Length: {len(raw_text)}")
        logger.debug(f"Raw response snippet: {raw_text[:500]}...")
        
        # Parse JSON response
        questions = _parse_gemini_response(raw_text, page_num)
        
        logger.info(f"Successfully extracted {len(questions)} questions from Page {page_num}")
        return questions
    
    except Exception as e:
        logger.error(f"Vision API analysis failed for Page {page_num}: {str(e)}")
        return []


def _parse_gemini_response(raw_text: str, page_num: int) -> List[Dict]:
    """
    Parse Gemini's JSON response and validate structure.
    """
    try:
        # Clean markdown code blocks
        clean_text = raw_text.strip()
        if clean_text.startswith("```json"):
            clean_text = clean_text[7:]
        elif clean_text.startswith("```"):
            clean_text = clean_text[3:]
        if clean_text.endswith("```"):
            clean_text = clean_text[:-3]
        clean_text = clean_text.strip()
        
        # Parse JSON
        result_json = json.loads(clean_text)
        
        # Extract questions array
        if isinstance(result_json, dict):
            questions = result_json.get("questions", [])
        elif isinstance(result_json, list):
            questions = result_json
        else:
            logger.error(f"Unexpected JSON structure: {type(result_json)}")
            return []
        
        # Validate and clean questions
        validated_questions = []
        for q in questions:
            if not isinstance(q, dict):
                continue
            
            # Ensure required fields
            if 'questionText' not in q:
                logger.warning(f"Question missing questionText: {q}")
                continue
            
            # Set defaults for missing fields
            validated_q = {
                'questionText': q.get('questionText', ''),
                'options': q.get('options', {}),
                'image': q.get('image'),
                'optionImages': q.get('optionImages', {}),
                'correctAnswer': q.get('correctAnswer'),
                'needsAnswer': q.get('needsAnswer', True),
                'type': q.get('type', 'single'),
                'metadata': q.get('metadata', {})
            }
            
            # Add page info to metadata
            if 'page' not in validated_q['metadata']:
                validated_q['metadata']['page'] = page_num
            
            validated_questions.append(validated_q)
        
        return validated_questions
    
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error for Page {page_num}: {e}")
        logger.error(f"Raw text: {raw_text[:1000]}")
        return []
    except Exception as e:
        logger.error(f"Response parsing failed: {e}")
        return []


async def fallback_to_deterministic(text_blocks: List[Dict], images: List[Dict], page_num: int) -> List[Dict]:
    """
    Fallback to deterministic extraction when AI fails.
    Uses regex-based question detection.
    """
    import re
    from ai_preview_importer.pdf_extractor_enhanced import (
        detect_question_anchors,
        attach_images_to_questions,
        format_questions_for_ai
    )
    
    logger.warning(f"Page {page_num}: Using fallback deterministic extraction")
    
    try:
        # Detect questions using regex
        candidate_questions = detect_question_anchors(text_blocks)
        
        # Attach images
        attach_images_to_questions(candidate_questions, images)
        
        # Format for output
        formatted = format_questions_for_ai(candidate_questions)
        
        # Convert to new format
        questions = []
        for fq in formatted:
            q_text = " ".join(fq.get('raw_question_lines', []))
            
            questions.append({
                'questionText': q_text,
                'options': fq.get('options', {}),
                'image': fq.get('image_id'),
                'optionImages': {},
                'correctAnswer': None,
                'needsAnswer': True,
                'type': 'single',
                'metadata': {
                    'page': page_num,
                    'source': 'fallback'
                }
            })
        
        logger.info(f"Fallback extracted {len(questions)} questions from Page {page_num}")
        return questions
    
    except Exception as e:
        logger.error(f"Fallback extraction failed: {e}")
        return []
