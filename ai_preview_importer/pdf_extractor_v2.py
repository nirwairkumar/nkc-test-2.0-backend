"""
Enhanced PDF Extractor V2 - With Spatial Analysis
Uses Python libraries: PyMuPDF, pdfplumber, PIL, NumPy
"""
import fitz  # PyMuPDF
import pdfplumber
import io
from typing import List, Dict, Tuple
from utils.logger import get_logger
from ai_preview_importer.spatial_analyzer import (
    detect_columns,
    calculate_reading_order,
    extract_font_metadata
)

logger = get_logger(__name__)


def extract_with_spatial_analysis(pdf_bytes: bytes) -> Dict:
    """
    Enhanced extraction that returns structured layout with spatial relationships.
    
    Returns:
    {
        'pages': {
            1: {
                'text_blocks': [...],
                'page_width': float,
                'page_height': float,
                'num_columns': int
            }
        }
    }
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    logger.info(f"Opened PDF with {len(doc)} pages for spatial analysis")
    
    all_text_blocks = []
    pages_data = {}
    
    # First pass: Extract all text blocks with basic info
    for page_num, page in enumerate(doc):
        page_dict = page.get_text("dict")
        blocks = page_dict.get("blocks", [])
        
        page_width = page.rect.width
        page_height = page.rect.height
        
        page_blocks = []
        
        for block in blocks:
            if block.get("type") == 0:  # Text block
                for line in block.get("lines", []):
                    line_text = "".join([span["text"] for span in line.get("spans", [])])
                    
                    if line_text.strip():
                        line_data = {
                            "page_num": page_num + 1,
                            "bbox": line["bbox"],
                            "text": line_text,
                            "source": "pymupdf"
                        }
                        page_blocks.append(line_data)
                        all_text_blocks.append(line_data)
        
        # Extract font metadata for this page
        page_blocks = extract_font_metadata(page, page_blocks)
        
        pages_data[page_num + 1] = {
            'text_blocks': page_blocks,
            'page_width': page_width,
            'page_height': page_height,
            'num_columns': 1  # Will be updated
        }
    
    # Second pass: Detect columns
    columns_per_page = detect_columns(all_text_blocks, pages_data[1]['page_width'] if pages_data else 600)
    
    for page_num, num_cols in columns_per_page.items():
        if page_num in pages_data:
            pages_data[page_num]['num_columns'] = num_cols
    
    # Third pass: Calculate reading order
    ordered_blocks = calculate_reading_order(all_text_blocks, columns_per_page)
    
    # Update pages_data with ordered blocks
    for page_num in pages_data:
        page_ordered_blocks = [b for b in ordered_blocks if b['page_num'] == page_num]
        pages_data[page_num]['text_blocks'] = page_ordered_blocks
    
    logger.info(f"Extracted {len(all_text_blocks)} text blocks with spatial analysis")
    
    return {
        'pages': pages_data,
        'total_pages': len(doc)
    }


def merge_text_blocks_into_paragraphs(text_blocks: List[Dict]) -> List[Dict]:
    """
    Merges consecutive text blocks that belong to the same paragraph.
    Uses spatial proximity and reading order.
    """
    if not text_blocks:
        return []
    
    paragraphs = []
    current_paragraph = {
        'text': text_blocks[0]['text'],
        'bbox': text_blocks[0]['bbox'],
        'page_num': text_blocks[0]['page_num'],
        'blocks': [text_blocks[0]]
    }
    
    for i in range(1, len(text_blocks)):
        prev_block = text_blocks[i-1]
        curr_block = text_blocks[i]
        
        # Check if blocks should be merged
        same_page = curr_block['page_num'] == prev_block['page_num']
        vertical_gap = curr_block['bbox'][1] - prev_block['bbox'][3]
        
        # Merge if on same page and close together (< 20 pixels)
        if same_page and vertical_gap < 20:
            current_paragraph['text'] += ' ' + curr_block['text']
            current_paragraph['blocks'].append(curr_block)
            # Update bbox to encompass both
            current_paragraph['bbox'] = _union_bbox(
                current_paragraph['bbox'],
                curr_block['bbox']
            )
        else:
            # Start new paragraph
            paragraphs.append(current_paragraph)
            current_paragraph = {
                'text': curr_block['text'],
                'bbox': curr_block['bbox'],
                'page_num': curr_block['page_num'],
                'blocks': [curr_block]
            }
    
    # Don't forget the last paragraph
    paragraphs.append(current_paragraph)
    
    logger.debug(f"Merged {len(text_blocks)} blocks into {len(paragraphs)} paragraphs")
    return paragraphs


def detect_question_patterns(text_blocks: List[Dict]) -> List[Dict]:
    """
    Enhanced question detection using multiple signals:
    - Numbering patterns
    - Font size/weight
    - Spatial gaps
    - Content semantics
    """
    import re
    
    question_candidates = []
    
    # Patterns for question numbering
    patterns = [
        r'^\s*(\d+)\.\s+',  # "1. "
        r'^\s*Q\.?\s*(\d+)',  # "Q1" or "Q. 1"
        r'^\s*Question\s+(\d+)',  # "Question 1"
        r'^\s*\((\d+)\)',  # "(1)"
        r'^\s*\[(\d+)\]',  # "[1]"
    ]
    
    for i, block in enumerate(text_blocks):
        text = block['text']
        is_question = False
        question_num = None
        
        # Check numbering patterns
        for pattern in patterns:
            match = re.match(pattern, text, re.IGNORECASE)
            if match:
                is_question = True
                question_num = int(match.group(1))
                break
        
        # Check font signals (bold or larger font often indicates questions)
        if block.get('is_bold') or block.get('font_size', 12) > 12:
            is_question = True
        
        # Check for large vertical gap before this block
        if i > 0:
            prev_block = text_blocks[i-1]
            if block['page_num'] == prev_block['page_num']:
                gap = block['bbox'][1] - prev_block['bbox'][3]
                if gap > 30:  # Large gap suggests new question
                    is_question = True
        
        if is_question:
            question_candidates.append({
                'block_index': i,
                'question_num': question_num,
                'text': text,
                'bbox': block['bbox'],
                'page_num': block['page_num'],
                'confidence': _calculate_question_confidence(block, text)
            })
    
    logger.debug(f"Detected {len(question_candidates)} question candidates")
    return question_candidates


def _union_bbox(bbox1: Tuple, bbox2: Tuple) -> Tuple:
    """Calculate union of two bounding boxes."""
    return (
        min(bbox1[0], bbox2[0]),
        min(bbox1[1], bbox2[1]),
        max(bbox1[2], bbox2[2]),
        max(bbox1[3], bbox2[3])
    )


def _calculate_question_confidence(block: Dict, text: str) -> float:
    """
    Calculate confidence that this block is a question start.
    Returns value between 0 and 1.
    """
    confidence = 0.5  # Base confidence
    
    # Boost for bold text
    if block.get('is_bold'):
        confidence += 0.2
    
    # Boost for larger font
    if block.get('font_size', 12) > 12:
        confidence += 0.15
    
    # Boost for question keywords
    question_keywords = ['what', 'which', 'who', 'where', 'when', 'why', 'how', 'explain', 'describe', 'calculate']
    text_lower = text.lower()
    if any(keyword in text_lower for keyword in question_keywords):
        confidence += 0.15
    
    return min(confidence, 1.0)


# Backward compatibility wrapper
def extract_text_blocks_v2(pdf_bytes: bytes) -> List[Dict]:
    """
    Wrapper that returns flat list of text blocks (backward compatible).
    """
    result = extract_with_spatial_analysis(pdf_bytes)
    
    all_blocks = []
    for page_data in result['pages'].values():
        all_blocks.extend(page_data['text_blocks'])
    
    return all_blocks
