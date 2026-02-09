from fastapi import APIRouter, HTTPException, Depends
from app.core.database import get_db
from supabase import Client
from typing import Optional, List, Dict, Any
from app.routers.tests.schemas import *
import uuid

router = APIRouter()

@router.get("/debug/schema")
async def debug_schema(db: Client = Depends(get_db)):
    try:
        # Check connection and columns
        response = db.table("tests").select("*").limit(1).execute()
        columns = list(response.data[0].keys()) if response.data else []
        
        # Check User Profile (FK Constraint Check)
        user_resp = db.auth.get_user()
        user_id = user_resp.user.id
        profile_resp = db.table("profiles").select("id").eq("id", user_id).execute()
        has_profile = len(profile_resp.data) > 0

        return {
            "status": "ok", 
            "connected": True, 
            "columns": columns,
            "has_sections": "sections" in columns,
            "has_profile": has_profile,
            "user_id": user_id
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@router.post("/")
async def create_test(
    payload: CreateTestRequest,
    db: Client = Depends(get_db)
):
    try:
        data = payload.dict(exclude_unset=True)
        try:
            # Try inserting with all fields (including new ones like sections)
            response = db.table("tests").insert(data).execute()
            # PostgREST returns list of inserted rows
            return response.data[0] if response.data else None
        except Exception as e:
            # If schema mismatch (missing columns for new features), retry with safe legacy fields
            print(f"Full insert failed (likely schema mismatch or syntax): {e}. Retrying with legacy fields only.")
            
            # Define fields that differ between old and new schema
            legacy_keys = {
                "title", "description", "questions", "created_by", "created_at", 
                "custom_id", "duration", "marks_per_question", "negative_marks", 
                "is_public", "visibility", "revision_notes", "institution_name",
                "institution_logo", "slug", "tags", "class_id", "sections", "test_id"
            }
            # Also creator_name/avatar might be missing if that migration wasn't run
            # But let's try to keep them if possible, or fall back further? 
            # For strict safety, let's include them in the 'legacy' set only if user confirmed.
            
            safe_data = {k: v for k, v in data.items() if k in legacy_keys}
            
            # Try insert again
            response = db.table("tests").insert(safe_data).execute()
            print("Legacy insert successful.")
            return response.data[0] if response.data else None
            
    except Exception as e:
        print(f"Error creating test: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{test_id}")
async def update_test(
    test_id: str,
    payload: Dict[str, Any], # Allow partial updates without strict validation or use UpdateTestRequest
    # Using Dict because frontend might send fields not in UpdateTestRequest if we lag behind
    db: Client = Depends(get_db)
):
    try:
        # Check if test exists
        # We can just update directly.
        
        # 1. Update Test
        try:
             response = db.table("tests").update(payload).eq("id", test_id).execute()
             if response.data:
                return response.data[0]
             return None
        except Exception as e:
            print(f"Full update failed: {e}. Retrying with legacy fields.")
            legacy_keys = {
                "title", "description", "questions", "created_by", "created_at", 
                "custom_id", "duration", "marks_per_question", "negative_marks", 
                "is_public", "visibility", "revision_notes", "institution_name",
                "institution_logo", "slug", "tags", "class_id"
            }
            safe_payload = {k: v for k, v in payload.items() if k in legacy_keys}
            response = db.table("tests").update(safe_payload).eq("id", test_id).execute()
            if response.data:
                return response.data[0]
            return None

    except Exception as e:
        print(f"Error updating test: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{test_id}")
async def delete_test(test_id: str, db: Client = Depends(get_db)):
    try:
        response = db.table("tests").delete().eq("id", test_id).execute()
        return {"success": True}
    except Exception as e:
        print(f"Error deleting test: {e}")
        raise HTTPException(status_code=500, detail=str(e))
