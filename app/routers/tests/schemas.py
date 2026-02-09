from pydantic import BaseModel
from typing import Optional, List, Dict, Any

class TestSection(BaseModel):
    id: str
    name: str
    instructions: Optional[str] = None
    marks_per_question: Optional[float] = 4
    negative_marks: Optional[float] = 1
    question_type: Optional[str] = "single"
    questions: List[Dict[str, Any]] = []

class CreateTestRequest(BaseModel):
    title: str
    description: Optional[str] = ""
    questions: Optional[List[Dict[str, Any]]] = []
    created_at: Optional[str] = None
    custom_id: Optional[str] = None
    marks_per_question: Optional[float] = 4
    negative_marks: Optional[float] = 1
    duration: Optional[int] = 30
    revision_notes: Optional[str] = None
    is_public: Optional[bool] = False
    visibility: Optional[str] = "public"
    creator_name: Optional[str] = None
    creator_avatar: Optional[str] = None
    created_by: str
    institution_name: Optional[str] = None
    institution_logo: Optional[str] = None
    slug: Optional[str] = None
    og_image: Optional[str] = None
    tags: Optional[List[str]] = []
    custom_category: Optional[str] = None
    class_id: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None
    has_scientific_calculator: Optional[bool] = False
    enable_section_mode: Optional[bool] = False
    sections: Optional[List[Dict[str, Any]]] = []
    section_marking_model: Optional[str] = "section-wise"

class UpdateTestRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    questions: Optional[List[Dict[str, Any]]] = None
    custom_id: Optional[str] = None
    marks_per_question: Optional[float] = None
    negative_marks: Optional[float] = None
    duration: Optional[int] = None
    revision_notes: Optional[str] = None
    is_public: Optional[bool] = None
    visibility: Optional[str] = None
    tags: Optional[List[str]] = None
    custom_category: Optional[str] = None
    class_id: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None
    has_scientific_calculator: Optional[bool] = None
    enable_section_mode: Optional[bool] = None
    sections: Optional[List[Dict[str, Any]]] = None
    section_marking_model: Optional[str] = None
    slug: Optional[str] = None
    og_image: Optional[str] = None
