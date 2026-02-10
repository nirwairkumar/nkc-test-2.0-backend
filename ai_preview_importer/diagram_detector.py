"""
Diagram Detector - Specialized extraction for diagrams, charts, and mathematical content
"""
import fitz
import io
import base64
import numpy as np
from PIL import Image
from typing import List, Dict, Tuple
from utils.logger import get_logger

logger = get_logger(__name__)

# Try to import OpenCV for advanced processing
try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    logger.warning("OpenCV not available. Advanced diagram detection disabled")


def detect_and_extract_diagrams(pdf_bytes: bytes) -> List[Dict]:
    """
    Detects and extracts diagrams, charts, and mathematical content from PDF.
    Returns list of diagram objects with metadata.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    diagrams = []
    
    for page_num, page in enumerate(doc):
        # Method 1: Extract vector graphics
        vector_diagrams = _extract_vector_graphics(page, page_num)
        diagrams.extend(vector_diagrams)
        
        # Method 2: Detect diagram regions using image analysis
        if CV2_AVAILABLE:
            region_diagrams = _detect_diagram_regions(page, page_num)
            diagrams.extend(region_diagrams)
        
        # Method 3: Extract mathematical equations/formulas
        equations = _extract_equations(page, page_num)
        diagrams.extend(equations)
    
    logger.info(f"Detected {len(diagrams)} diagrams/charts/equations")
    return diagrams


def _extract_vector_graphics(page, page_num: int) -> List[Dict]:
    """
    Extracts vector graphics (lines, curves, shapes) as rasterized images.
    These are often diagrams, flowcharts, or geometric figures.
    """
    diagrams = []
    
    try:
        # Get all drawing commands on the page
        drawings = page.get_drawings()
        
        if not drawings:
            return diagrams
        
        # Group drawings by proximity to identify diagram regions
        diagram_regions = _group_drawings_into_regions(drawings)
        
        for region_idx, region in enumerate(diagram_regions):
            # Calculate bounding box for this region
            bbox = _calculate_region_bbox(region)
            
            # Skip very small regions (likely decorative elements)
            width = bbox[2] - bbox[0]
            height = bbox[3] - bbox[1]
            if width < 50 or height < 50:
                continue
            
            # Render this region as an image
            # Create a clip rect with some padding
            clip_rect = fitz.Rect(
                bbox[0] - 5,
                bbox[1] - 5,
                bbox[2] + 5,
                bbox[3] + 5
            )
            
            # Render at 2x resolution for quality
            mat = fitz.Matrix(2, 2)
            pix = page.get_pixmap(matrix=mat, clip=clip_rect, alpha=False)
            
            # Convert to PIL Image
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            
            # Convert to base64
            img_bytes = io.BytesIO()
            img.save(img_bytes, format='PNG')
            img_bytes.seek(0)
            b64_str = base64.b64encode(img_bytes.read()).decode('utf-8')
            
            diagrams.append({
                'page_num': page_num + 1,
                'bbox': bbox,
                'base64': f"data:image/png;base64,{b64_str}",
                'type': 'diagram',
                'source': 'vector_graphics',
                'width': pix.width,
                'height': pix.height
            })
        
        logger.debug(f"Page {page_num + 1}: Extracted {len(diagrams)} vector diagrams")
    
    except Exception as e:
        logger.warning(f"Vector graphics extraction failed for page {page_num + 1}: {e}")
    
    return diagrams


def _detect_diagram_regions(page, page_num: int) -> List[Dict]:
    """
    Uses computer vision to detect diagram-like regions in the page.
    Looks for areas with high edge density, geometric shapes, etc.
    """
    diagrams = []
    
    try:
        # Render page as image
        mat = fitz.Matrix(2, 2)  # 2x zoom
        pix = page.get_pixmap(matrix=mat, alpha=False)
        
        # Convert to OpenCV format
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        img_array = np.array(img)
        img_cv = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
        
        # Convert to grayscale
        gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
        
        # Edge detection
        edges = cv2.Canny(gray, 50, 150)
        
        # Find contours (potential diagram boundaries)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        for contour in contours:
            # Get bounding rectangle
            x, y, w, h = cv2.boundingRect(contour)
            
            # Filter by size (diagrams are usually substantial)
            if w < 100 or h < 100:
                continue
            
            # Calculate edge density in this region
            roi = edges[y:y+h, x:x+w]
            edge_density = np.sum(roi > 0) / (w * h)
            
            # High edge density suggests a diagram
            if edge_density > 0.05:  # Threshold for diagram detection
                # Extract this region
                region_img = img_cv[y:y+h, x:x+w]
                
                # Convert to base64
                _, buffer = cv2.imencode('.png', region_img)
                b64_str = base64.b64encode(buffer).decode('utf-8')
                
                # Adjust bbox for 2x zoom
                bbox = (x/2, y/2, (x+w)/2, (y+h)/2)
                
                diagrams.append({
                    'page_num': page_num + 1,
                    'bbox': bbox,
                    'base64': f"data:image/png;base64,{b64_str}",
                    'type': 'diagram',
                    'source': 'cv_detection',
                    'width': w,
                    'height': h,
                    'edge_density': float(edge_density)
                })
        
        logger.debug(f"Page {page_num + 1}: Detected {len(diagrams)} diagram regions via CV")
    
    except Exception as e:
        logger.warning(f"CV diagram detection failed for page {page_num + 1}: {e}")
    
    return diagrams


def _extract_equations(page, page_num: int) -> List[Dict]:
    """
    Attempts to identify and extract mathematical equations/formulas.
    These often appear as special fonts or symbols.
    """
    equations = []
    
    try:
        # Get text with font information
        page_dict = page.get_text("dict")
        blocks = page_dict.get("blocks", [])
        
        for block in blocks:
            if block.get("type") != 0:  # Skip non-text blocks
                continue
            
            for line in block.get("lines", []):
                # Check if line contains mathematical symbols
                line_text = "".join([span["text"] for span in line.get("spans", [])])
                
                if _contains_math_symbols(line_text):
                    # This might be an equation
                    bbox = line["bbox"]
                    
                    # Render this specific region
                    clip_rect = fitz.Rect(bbox)
                    mat = fitz.Matrix(3, 3)  # Higher resolution for equations
                    pix = page.get_pixmap(matrix=mat, clip=clip_rect, alpha=False)
                    
                    # Convert to base64
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    img_bytes = io.BytesIO()
                    img.save(img_bytes, format='PNG')
                    img_bytes.seek(0)
                    b64_str = base64.b64encode(img_bytes.read()).decode('utf-8')
                    
                    equations.append({
                        'page_num': page_num + 1,
                        'bbox': bbox,
                        'base64': f"data:image/png;base64,{b64_str}",
                        'type': 'equation',
                        'source': 'math_detection',
                        'text': line_text,
                        'width': pix.width,
                        'height': pix.height
                    })
        
        logger.debug(f"Page {page_num + 1}: Extracted {len(equations)} equations")
    
    except Exception as e:
        logger.warning(f"Equation extraction failed for page {page_num + 1}: {e}")
    
    return equations


def classify_diagram_type(diagram: Dict) -> str:
    """
    Attempts to classify the type of diagram.
    Returns: 'flowchart', 'graph', 'chart', 'geometric', 'equation', 'unknown'
    """
    # This is a simplified classifier
    # In a production system, you might use ML models
    
    diagram_type = diagram.get('type', 'unknown')
    
    if diagram_type == 'equation':
        return 'equation'
    
    # Use aspect ratio and size as simple heuristics
    width = diagram.get('width', 0)
    height = diagram.get('height', 0)
    
    if width == 0 or height == 0:
        return 'unknown'
    
    aspect_ratio = width / height
    
    if 0.8 <= aspect_ratio <= 1.2:
        return 'geometric'  # Square-ish diagrams
    elif aspect_ratio > 1.5:
        return 'chart'  # Wide diagrams (often charts/graphs)
    else:
        return 'diagram'  # Default


# Helper functions

def _group_drawings_into_regions(drawings: List, proximity_threshold: float = 50) -> List[List]:
    """
    Groups drawing commands that are close together into diagram regions.
    """
    if not drawings:
        return []
    
    # Extract bounding boxes from drawings
    bboxes = []
    for drawing in drawings:
        rect = drawing.get('rect')
        if rect:
            bboxes.append((rect.x0, rect.y0, rect.x1, rect.y1))
    
    if not bboxes:
        return []
    
    # Simple clustering based on proximity
    regions = [[bboxes[0]]]
    
    for bbox in bboxes[1:]:
        added = False
        for region in regions:
            # Check if bbox is close to any bbox in this region
            for existing_bbox in region:
                if _bboxes_are_close(bbox, existing_bbox, proximity_threshold):
                    region.append(bbox)
                    added = True
                    break
            if added:
                break
        
        if not added:
            regions.append([bbox])
    
    return regions


def _calculate_region_bbox(bboxes: List[Tuple]) -> Tuple:
    """Calculate union bounding box for a region."""
    x0 = min(b[0] for b in bboxes)
    y0 = min(b[1] for b in bboxes)
    x1 = max(b[2] for b in bboxes)
    y1 = max(b[3] for b in bboxes)
    return (x0, y0, x1, y1)


def _bboxes_are_close(bbox1: Tuple, bbox2: Tuple, threshold: float) -> bool:
    """Check if two bounding boxes are within threshold distance."""
    center1 = ((bbox1[0] + bbox1[2]) / 2, (bbox1[1] + bbox1[3]) / 2)
    center2 = ((bbox2[0] + bbox2[2]) / 2, (bbox2[1] + bbox2[3]) / 2)
    
    distance = np.sqrt((center1[0] - center2[0])**2 + (center1[1] - center2[1])**2)
    return distance <= threshold


def _contains_math_symbols(text: str) -> bool:
    """Check if text contains mathematical symbols."""
    math_symbols = ['∫', '∑', '∏', '√', '∞', '≈', '≠', '≤', '≥', '±', '×', '÷', 
                    '∂', '∇', 'α', 'β', 'γ', 'δ', 'θ', 'λ', 'μ', 'π', 'σ', 'ω',
                    '∈', '∉', '⊂', '⊃', '∪', '∩', '→', '⇒', '⇔']
    
    # Also check for common equation patterns
    equation_patterns = ['=', '+', '-', '/', '^', '(', ')', '[', ']']
    
    # Count math symbols
    math_count = sum(1 for char in text if char in math_symbols)
    pattern_count = sum(1 for char in text if char in equation_patterns)
    
    # If more than 20% of characters are math-related, it's likely an equation
    total_chars = len(text)
    if total_chars > 0:
        math_ratio = (math_count + pattern_count) / total_chars
        return math_ratio > 0.2
    
    return False
