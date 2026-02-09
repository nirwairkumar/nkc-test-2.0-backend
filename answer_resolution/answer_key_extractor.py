import re
from utils.logger import get_logger

logger = get_logger(__name__)

def extract_answer_key(text_blocks):
    """
    Scans text blocks for an answer key section.
    Returns a dict {question_number: "A/B/C/D"}.
    """
    answer_key = {}
    
    # Simple heuristic: Look for block containing "Answer Key" or "Answers"
    # followed by "1. A", "2. B" etc.
    
    # This is a stub implementation for Phase 2 as requested.
    # In a real scenario, this would be robust regex parsing.
    
    logger.info("Answer key extraction (Stub) - No keys extracted")
    return answer_key
