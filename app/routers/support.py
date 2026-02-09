from fastapi import APIRouter, HTTPException, Depends
from app.core.database import get_db
from supabase import Client
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

class FeedbackCreate(BaseModel):
    test_id: str
    rating: int
    comment: Optional[str] = None
    custom_test_id: Optional[str] = None
    sender_name: Optional[str] = None
    sender_email: Optional[str] = None
    receiver_name: Optional[str] = None
    receiver_email: Optional[str] = None

@router.post("/feedback")
async def submit_feedback(payload: FeedbackCreate, db: Client = Depends(get_db)):
    try:
        data = payload.dict(exclude_unset=True)
        response = db.table("feedback").insert(data).execute()
        return response.data
    except Exception as e:
        print(f"Error submitting feedback: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class SupportMessage(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None
    message: str

@router.post("/message")
async def send_support_message(payload: SupportMessage, db: Client = Depends(get_db)):
    try:
        data = payload.dict()
        response = db.table("support_messages").insert(data).execute()
        return {"success": True, "message": "Support message saved successfully", "data": response.data}
    except Exception as e:
        print(f"Error sending support message: {e}")
        raise HTTPException(status_code=500, detail=str(e))
