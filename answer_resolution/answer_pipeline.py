from answer_resolution.answer_key_extractor import extract_answer_key
from answer_resolution.answer_enricher import enrich_questions_with_answers
from ai_preview_importer.pdf_extractor import extract_text_blocks # Reuse this if needed
from utils.logger import get_logger

logger = get_logger(__name__)

def resolve_answers(questions, file_bytes):
    """
    Pipeline to extract answers and enrich questions.
    """
    # We might need to re-extract text or pass it in. 
    # For now, let's assume we re-extract or it's cheap enough.
    # Or ideally, pass the extracted blocks from preview_pipeline.
    
    # For this stub, we'll re-extract to keep interfaces clean unless we refactor.
    # But since preview_pipeline didn't return blocks, we re-extract or just return questions as is for now if cheap.
    # Actually, let's just use the stub.
    
    blocks = extract_text_blocks(file_bytes)
    answer_key = extract_answer_key(blocks)
    enriched_questions = enrich_questions_with_answers(questions, answer_key)
    
    return enriched_questions
