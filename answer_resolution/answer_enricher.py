from utils.logger import get_logger

logger = get_logger(__name__)

def enrich_questions_with_answers(questions, answer_key):
    """
    Updates questions in-place with correct answers from the key.
    Sets needsAnswer = False if answer found.
    """
    if not answer_key:
        return questions
        
    for q in questions:
        q_id = q['id']
        if q_id in answer_key:
            q['correctAnswer'] = answer_key[q_id]
            q['needsAnswer'] = False
            
    logger.info(f"Enriched {len(questions)} questions with answers")
    return questions
