"""
Spatial Analyzer - Analyzes spatial relationships between text blocks and images
"""
import numpy as np
from typing import List, Dict, Tuple
from utils.logger import get_logger

logger = get_logger(__name__)


def analyze_spatial_relationships(text_blocks: List[Dict], images: List[Dict]) -> List[Dict]:
    """
    Analyzes spatial relationships between text blocks and images.
    Returns a list of relationship objects.
    """
    relationships = []
    
    for img in images:
        img_bbox = img['bbox']
        img_center = _get_center(img_bbox)
        page_num = img['page_num']
        
        # Find text blocks on the same page
        page_blocks = [b for b in text_blocks if b['page_num'] == page_num]
        
        if not page_blocks:
            continue
        
        # Find closest text block
        closest_block = None
        min_distance = float('inf')
        relationship_type = None
        
        for block in page_blocks:
            block_bbox = block['bbox']
            
            # Check if image is contained within text block
            if _is_contained(img_bbox, block_bbox):
                relationships.append({
                    'text_block_id': id(block),
                    'image_id': img.get('id', f"img_{page_num}"),
                    'relationship': 'contained',
                    'distance': 0,
                    'confidence': 1.0
                })
                closest_block = block
                break
            
            # Calculate distance and direction
            distance, direction = _calculate_distance_and_direction(img_bbox, block_bbox)
            
            if distance < min_distance:
                min_distance = distance
                closest_block = block
                relationship_type = direction
        
        if closest_block and relationship_type:
            relationships.append({
                'text_block_id': id(closest_block),
                'image_id': img.get('id', f"img_{page_num}"),
                'relationship': relationship_type,
                'distance': min_distance,
                'confidence': _calculate_confidence(min_distance)
            })
    
    logger.info(f"Analyzed {len(relationships)} spatial relationships")
    return relationships


def detect_columns(text_blocks: List[Dict], page_width: float) -> Dict[int, int]:
    """
    Detects multi-column layouts by analyzing x-coordinates of text blocks.
    Returns a dict mapping page_num to number of columns.
    """
    pages_columns = {}
    
    # Group by page
    pages = {}
    for block in text_blocks:
        p = block['page_num']
        if p not in pages:
            pages[p] = []
        pages[p].append(block)
    
    for page_num, blocks in pages.items():
        if not blocks:
            pages_columns[page_num] = 1
            continue
        
        # Get x-coordinates of left edges
        x_coords = [b['bbox'][0] for b in blocks]
        
        # Cluster x-coordinates to find column starts
        clusters = _cluster_coordinates(x_coords, threshold=page_width * 0.1)
        
        num_columns = len(clusters)
        pages_columns[page_num] = num_columns
        
        logger.debug(f"Page {page_num}: Detected {num_columns} column(s)")
    
    return pages_columns


def calculate_reading_order(text_blocks: List[Dict], columns_per_page: Dict[int, int]) -> List[Dict]:
    """
    Calculates proper reading order considering multi-column layouts.
    Returns text blocks with added 'reading_order' field.
    """
    # Group by page
    pages = {}
    for block in text_blocks:
        p = block['page_num']
        if p not in pages:
            pages[p] = []
        pages[p].append(block)
    
    ordered_blocks = []
    global_order = 1
    
    for page_num in sorted(pages.keys()):
        blocks = pages[page_num]
        num_columns = columns_per_page.get(page_num, 1)
        
        if num_columns == 1:
            # Simple top-to-bottom sorting
            blocks.sort(key=lambda b: (b['bbox'][1], b['bbox'][0]))
        else:
            # Multi-column: sort by column, then by y-coordinate
            blocks = _sort_multi_column(blocks, num_columns)
        
        # Assign reading order
        for block in blocks:
            block['reading_order'] = global_order
            global_order += 1
            ordered_blocks.append(block)
    
    return ordered_blocks


def extract_font_metadata(page, text_blocks: List[Dict]) -> List[Dict]:
    """
    Extracts font metadata (size, bold, italic) for text blocks.
    Requires PyMuPDF page object.
    """
    try:
        page_dict = page.get_text("dict")
        blocks_dict = page_dict.get("blocks", [])
        
        # Create a mapping of bbox to font info
        font_map = {}
        
        for block in blocks_dict:
            if block.get("type") == 0:  # Text block
                for line in block.get("lines", []):
                    line_bbox = line["bbox"]
                    
                    # Get font info from first span (usually representative)
                    spans = line.get("spans", [])
                    if spans:
                        span = spans[0]
                        font_info = {
                            'size': span.get('size', 12),
                            'font': span.get('font', 'unknown'),
                            'flags': span.get('flags', 0)  # Bit flags for bold, italic, etc.
                        }
                        font_map[line_bbox] = font_info
        
        # Match font info to text blocks
        for block in text_blocks:
            bbox = tuple(block['bbox'])
            
            # Find matching font info (exact or closest match)
            if bbox in font_map:
                font_info = font_map[bbox]
            else:
                # Find closest bbox
                font_info = _find_closest_font_info(bbox, font_map)
            
            if font_info:
                block['font_size'] = font_info['size']
                block['font_name'] = font_info['font']
                block['is_bold'] = bool(font_info['flags'] & 2**4)  # Bold flag
                block['is_italic'] = bool(font_info['flags'] & 2**1)  # Italic flag
            else:
                block['font_size'] = 12
                block['font_name'] = 'unknown'
                block['is_bold'] = False
                block['is_italic'] = False
        
        return text_blocks
    
    except Exception as e:
        logger.warning(f"Font metadata extraction failed: {e}")
        # Add default values
        for block in text_blocks:
            block['font_size'] = 12
            block['font_name'] = 'unknown'
            block['is_bold'] = False
            block['is_italic'] = False
        return text_blocks


# Helper functions

def _get_center(bbox: Tuple[float, float, float, float]) -> Tuple[float, float]:
    """Calculate center point of a bounding box."""
    return ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)


def _is_contained(inner_bbox: Tuple, outer_bbox: Tuple) -> bool:
    """Check if inner_bbox is contained within outer_bbox."""
    return (outer_bbox[0] <= inner_bbox[0] and
            outer_bbox[1] <= inner_bbox[1] and
            outer_bbox[2] >= inner_bbox[2] and
            outer_bbox[3] >= inner_bbox[3])


def _calculate_distance_and_direction(bbox1: Tuple, bbox2: Tuple) -> Tuple[float, str]:
    """
    Calculate distance and direction between two bounding boxes.
    Returns (distance, direction) where direction is 'above', 'below', 'left', 'right'.
    """
    center1 = _get_center(bbox1)
    center2 = _get_center(bbox2)
    
    dx = center2[0] - center1[0]
    dy = center2[1] - center1[1]
    
    distance = np.sqrt(dx**2 + dy**2)
    
    # Determine primary direction
    if abs(dy) > abs(dx):
        direction = 'below' if dy > 0 else 'above'
    else:
        direction = 'right' if dx > 0 else 'left'
    
    return distance, direction


def _calculate_confidence(distance: float) -> float:
    """Calculate confidence score based on distance (closer = higher confidence)."""
    # Exponential decay: confidence = e^(-distance/100)
    return np.exp(-distance / 100)


def _cluster_coordinates(coords: List[float], threshold: float) -> List[List[float]]:
    """Simple clustering of coordinates."""
    if not coords:
        return []
    
    sorted_coords = sorted(coords)
    clusters = [[sorted_coords[0]]]
    
    for coord in sorted_coords[1:]:
        if coord - clusters[-1][-1] <= threshold:
            clusters[-1].append(coord)
        else:
            clusters.append([coord])
    
    return clusters


def _sort_multi_column(blocks: List[Dict], num_columns: int) -> List[Dict]:
    """Sort blocks for multi-column layout."""
    # Get x-coordinates and cluster them
    x_coords = [b['bbox'][0] for b in blocks]
    clusters = _cluster_coordinates(x_coords, threshold=50)
    
    # Assign column to each block
    for block in blocks:
        x = block['bbox'][0]
        for col_idx, cluster in enumerate(clusters):
            if any(abs(x - c) < 50 for c in cluster):
                block['column'] = col_idx
                break
        else:
            block['column'] = 0
    
    # Sort by column, then by y-coordinate
    blocks.sort(key=lambda b: (b.get('column', 0), b['bbox'][1], b['bbox'][0]))
    
    return blocks


def _find_closest_font_info(target_bbox: Tuple, font_map: Dict) -> Dict:
    """Find closest font info for a bbox."""
    if not font_map:
        return None
    
    target_center = _get_center(target_bbox)
    min_distance = float('inf')
    closest_info = None
    
    for bbox, info in font_map.items():
        center = _get_center(bbox)
        distance = np.sqrt((center[0] - target_center[0])**2 + (center[1] - target_center[1])**2)
        
        if distance < min_distance:
            min_distance = distance
            closest_info = info
    
    return closest_info
