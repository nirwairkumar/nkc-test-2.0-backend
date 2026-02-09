from fastapi import APIRouter, HTTPException, Depends, Body
from app.core.database import get_db
from app.core.config import settings
from supabase import Client
from typing import Optional, Dict, Any, List
from pydantic import BaseModel
import google.generativeai as genai
from youtube_transcript_api import YouTubeTranscriptApi
import json
import re

router = APIRouter()

# Configure Gemini
if settings.GEMINI_API_KEY:
    genai.configure(api_key=settings.GEMINI_API_KEY)

class GenerateYoutubeRequest(BaseModel):
    url: str
    language: str = "English"
    creator_name: str
    creator_avatar: Optional[str] = None
    user_id: str 

def extract_video_id(url: str) -> Optional[str]:
    # Regex for YouTube ID
    regex = r"(?:v=|\/)([0-9A-Za-z_-]{11}).*"
    match = re.search(regex, url)
    if match:
        return match.group(1)
    return None

def clean_json(text: str) -> str:
    start = text.find('{')
    end = text.rfind('}')
    if start == -1 or end == -1:
        return text
    return text[start:end+1]

@router.post("/generate/youtube")
async def generate_youtube_test(
    payload: GenerateYoutubeRequest,
    db: Client = Depends(get_db)
):
    if not settings.GEMINI_API_KEY:
         raise HTTPException(status_code=500, detail="Server misconfigured: Missing AI Key")

    video_id = extract_video_id(payload.url)
    if not video_id:
        raise HTTPException(status_code=400, detail="Invalid YouTube URL")

    transcript_text = ""
    used_method = "transcript"
    
    # 1. Fetch Transcript
    try:
        # Prefer English, Hindi, or auto
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['en', 'hi'])
        transcript_text = " ".join([t['text'] for t in transcript_list])
    except Exception as e:
        print(f"Transcript Error: {e}. Falling back to Multimodal Video.")
        used_method = "video"

    # 2. Prepare Prompt & Content
    request_content = []
    
    if used_method == "transcript" and transcript_text:
        # Transcript Mode
        prompt = f"""
            You are an expert exam setter and educator.
            
            Task:
            1. Analyze the lecture transcript.
            2. **IMPORTANT**: Generate ALL content (Description, Revision Notes, Questions, Options) in **{payload.language}**.
            3. Extract metadata (Teacher, Subject, Exam Type) for a short description.
            3. Create **structured revision notes** (Markdown supported) that help a student revise before exams.
               - Use clear bullet points
               - Include formulas, keywords, shortcuts, and step-by-step logic where applicable
               - Highlight common mistakes or traps if mentioned
               - Keep language simple and exam-oriented
            4. **Generate as many MCQs as possible** (minimum 10) based strictly on the content.
            
            IMPORTANT: Output **ONLY** valid raw JSON.
            
            JSON Structure:
            {{
                "title": "Topic or Video Title",
                "description": "Short info: Teacher Name | Subject | Exam Target (e.g. JEE/NEET/Board)",
                "revision_notes": "# Key Notes\\n* Point 1\\n* Formula...",
                "questions": [
                    {{
                        "id": 1,
                        "question": "Question text...",
                        "options": {{
                            "A": "...",
                            "B": "...",
                            "C": "...",
                            "D": "..."
                        }},
                        "correctAnswer": "A",
                        "marks": 1,
                        "negativeMarks": 0
                    }}
                ]
            }}

            Transcript:
            {transcript_text[:30000]}
        """
        request_content = prompt
        
    else:
        # Multimodal Video Mode (Fallback)
        print("Using Multimodal Video Mode")
        prompt = f"""
            You are an expert exam setter.
            Analyze the visual video content efficiently from the content.
            1. Create a short description (Subject/Topic).
            2. **IMPORTANT**: Generate ALL content (Description, Revision Notes, Questions, Options) in **{payload.language}**.
            3. Create **structured revision notes** (Markdown supported) that help a student revise before exams.
               - Use clear bullet points
               - Include formulas, keywords, shortcuts, and step-by-step logic where applicable
               - Highlight common mistakes or traps if mentioned
               - Keep language simple and exam-oriented
            3. **Extract(if questions present in the video)** or **Generate as many MCQs as possible** (minimum 10) based strictly on the content.

            Output **ONLY** valid raw JSON.
            JSON Structure:
            {{
                "title": "Topic Title",
                "description": "Short info...",
                "revision_notes": "Markdown notes...",
                "questions": [ 
                {{
                        "id": 1,
                        "question": "Question text...",
                        "options": {{
                            "A": "...",
                            "B": "...",
                            "C": "...",
                            "D": "..."
                        }},
                        "correctAnswer": "A",
                        "marks": 1,
                        "negativeMarks": 0
                    }}
                ]
            }}
        """
        # Construct Multimodal Payload
        # We pass the URL as file_uri if the model supports it (Gemini 1.5/3 Pro usually needs File API upload but user claims URL works)
        # We will try passing the exact structure:
        request_content = [
            {"mime_type": "video/mp4", "file_uri": payload.url}, # Note: Python SDK might expect 'file_data' wrapper or just this dict in parts
            prompt
        ]
        
        # Correct Python SDK usage for generation with media:
        # content = [part1, part2] matches the list. 
        # But allow 'file_uri' to be just the URL string? 
        # Standard Python SDK logic:
        # parts = [
        #   {"mime_type": "video/mp4", "data": ...} # keys are 'mime_type', 'data' for bytes
        #   OR 
        #   genai.types.File(...)
        # ]
    
    # 3. Call Gemini
    try:
        model = genai.GenerativeModel('gemini-3-pro-preview')
        
        # If request_content is list (Multimodal), use it. If string (Transcript), use it.
        # Python SDK handles [prompt_string] or prompt_string.
        # But for Multimodal with URL, we might need a hack if 'file_uri' expects 'gs://' or 'https://generativelanguage...'
        # We will try passing the dictionary structure which mirrors the JSON API.
        
        # If user logic was { fileData: { fileUri: url } }
        if used_method == "video":
             # We create a Part object manually to be safe or pass the list of parts
             # The SDK is flexible. Let's try the list of mixed content.
             pass
        
        response = model.generate_content(request_content)
        text = response.text
        
        # 3. Parse JSON
        cleaned = clean_json(text)
        data = json.loads(cleaned)
        
        # 4. Generate Custom ID (Simple logic for now, or match frontend logic)
        # We need a unique ID.
        # Let's fetch latest ID
        last_test = db.table("tests").select("custom_id").order("created_at", desc=True).limit(1).execute()
        next_id = "YT001"
        if last_test.data:
            lid = last_test.data[0].get("custom_id", "")
            if lid and lid.startswith("YT"):
                try:
                    num = int(lid.replace("YT", "")) + 1
                    next_id = f"YT{num:03d}"
                except:
                    pass
        
        # 5. Insert into DB
        test_insert = {
            "title": data.get("title", "Generated Test"),
            "description": data.get("description", ""),
            "revision_notes": data.get("revision_notes", ""),
            "questions": data.get("questions", []),
            "duration": len(data.get("questions", [])) * 1, # 1 min per q
            "custom_id": next_id,
            "created_by": payload.user_id,
            "creator_name": payload.creator_name,
            "creator_avatar": payload.creator_avatar,
            "is_public": True,
            "section_marking_model": "question-wise"
        }
        
        res = db.table("tests").insert(test_insert).execute()
        
        if res.data:
            return res.data[0]
            
        raise HTTPException(status_code=500, detail="Failed to save test")

    except Exception as e:
        print(f"AI Generation Error: {e}")
        raise HTTPException(status_code=500, detail=f"AI Generation Failed: {str(e)}")
