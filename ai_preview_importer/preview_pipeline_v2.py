"""
Enhanced Preview Pipeline V2 - Integrates all improved components
"""
import asyncio
from typing import Dict, List
from utils.logger import get_logger

# Import V2 extractors
from ai_preview_importer.pdf_extractor_v2 import extract_with_spatial_analysis
from ai_preview_importer.image_extractor_v2 import extract_all_visual_elements
from ai_preview_importer.spatial_analyzer import analyze_spatial_relationships
from ai_preview_importer.ai_reasoner_v2 import analyze_with_vision_and_text, fallback_to_deterministic

logger = get_logger(__name__)


async def run_enhanced_pipeline(file_bytes: bytes) -> Dict:
    """
    Enhanced PDF processing pipeline with spatial analysis and vision API.
    
    Process:
    1. Extract text with spatial analysis (columns, reading order, fonts)
    2. Extract all visual elements (images, diagrams, equations)
    3. Analyze spatial relationships between text and images
    4. Use Gemini Vision API to reconstruct questions accurately
    5. Fallback to deterministic extraction if AI fails
    
    Returns:
    {
        'questions': [...],
        'canConfirm': bool,
        'unansweredCount': int
    }
    """
    try:
        logger.info("Starting enhanced PDF pipeline...")
        
        # Step 1: Extract text with spatial analysis
        logger.info("Step 1: Extracting text with spatial analysis...")
        text_data = extract_with_spatial_analysis(file_bytes)
        pages_data = text_data['pages']
        
        # Step 2: Extract all visual elements
        logger.info("Step 2: Extracting visual elements (images, diagrams, equations)...")
        all_images = extract_all_visual_elements(file_bytes)
        
        # Group images by page
        images_by_page = {}
        for img in all_images:
            p = img['page_num']
            if p not in images_by_page:
                images_by_page[p] = []
            images_by_page[p].append(img)
        
        # Step 3: Analyze spatial relationships
        logger.info("Step 3: Analyzing spatial relationships...")
        all_text_blocks = []
        for page_data in pages_data.values():
            all_text_blocks.extend(page_data['text_blocks'])
        
        spatial_relationships = analyze_spatial_relationships(all_text_blocks, all_images)
        
        # Group relationships by page
        relationships_by_page = {}
        for rel in spatial_relationships:
            # Find which page this relationship belongs to
            for page_num, page_data in pages_data.items():
                for block in page_data['text_blocks']:
                    if id(block) == rel['text_block_id']:
                        if page_num not in relationships_by_page:
                            relationships_by_page[page_num] = []
                        relationships_by_page[page_num].append(rel)
                        break
        
        # Step 4: Process each page with Gemini Vision API
        logger.info("Step 4: Processing pages with Gemini Vision API...")
        final_questions = []
        global_id_counter = 1
        
        for page_num in sorted(pages_data.keys()):
            page_data = pages_data[page_num]
            page_images = images_by_page.get(page_num, [])
            page_relationships = relationships_by_page.get(page_num, [])
            
            logger.info(f"Processing Page {page_num}...")
            logger.debug(f"  - Text blocks: {len(page_data['text_blocks'])}")
            logger.debug(f"  - Images: {len(page_images)}")
            logger.debug(f"  - Relationships: {len(page_relationships)}")
            
            # Analyze with Vision API
            page_questions = await analyze_with_vision_and_text(
                text_blocks=page_data['text_blocks'],
                images=page_images,
                spatial_relationships=page_relationships,
                page_num=page_num,
                page_layout={
                    'num_columns': page_data.get('num_columns', 1),
                    'page_width': page_data.get('page_width'),
                    'page_height': page_data.get('page_height')
                }
            )
            
            # Fallback if AI returns nothing
            if not page_questions or len(page_questions) == 0:
                logger.warning(f"Page {page_num}: Vision API returned no questions. Using fallback...")
                page_questions = await fallback_to_deterministic(
                    page_data['text_blocks'],
                    page_images,
                    page_num
                )
            
            # Post-process: Resolve image IDs to base64
            page_img_map = {img['id']: img['base64'] for img in page_images}
            
            for q in page_questions:
                # Assign global ID
                q['id'] = global_id_counter
                global_id_counter += 1
                
                # Resolve question image
                if q.get('image') and q['image'] in page_img_map:
                    q['image'] = page_img_map[q['image']]
                else:
                    q['image'] = None
                
                # Resolve option images
                if q.get('optionImages'):
                    for opt_key, img_id in q['optionImages'].items():
                        if img_id and img_id in page_img_map:
                            q['optionImages'][opt_key] = page_img_map[img_id]
                        else:
                            q['optionImages'][opt_key] = None
                else:
                    q['optionImages'] = {k: None for k in ["A", "B", "C", "D"]}
                
                final_questions.append(q)
        
        # Step 5: Calculate stats
        unanswered_count = sum(1 for q in final_questions if q.get('needsAnswer'))
        can_confirm = unanswered_count == 0
        
        logger.info(f"Enhanced pipeline complete. Generated {len(final_questions)} questions.")
        logger.info(f"  - Unanswered: {unanswered_count}")
        logger.info(f"  - Can confirm: {can_confirm}")
        
        if len(final_questions) == 0:
            logger.error("CRITICAL: Pipeline produced 0 questions!")
            raise ValueError("Pipeline failure: Zero questions generated")
        
        return {
            "questions": final_questions,
            "canConfirm": can_confirm,
            "unansweredCount": unanswered_count
        }
    
    except Exception as e:
        logger.error(f"Enhanced pipeline failed: {str(e)}")
        raise e


# Feature flag to switch between old and new pipeline
USE_ENHANCED_PIPELINE = True


async def run_preview_pipeline_with_feature_flag(file_bytes: bytes) -> Dict:
    """
    Wrapper that allows switching between old and new pipeline.
    Set USE_ENHANCED_PIPELINE = True to use the new pipeline.
    """
    if USE_ENHANCED_PIPELINE:
        logger.info("Using ENHANCED pipeline (V2)")
        return await run_enhanced_pipeline(file_bytes)
    else:
        logger.info("Using ORIGINAL pipeline (V1)")
        from ai_preview_importer.preview_pipeline import run_preview_pipeline
        return await run_preview_pipeline(file_bytes)
