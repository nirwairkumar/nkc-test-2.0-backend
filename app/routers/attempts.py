from fastapi import APIRouter, HTTPException, Depends, Request
from app.core.database import get_db
from supabase import Client
from pydantic import BaseModel
from typing import Optional, Dict, Any, List

router = APIRouter()

class SaveAttemptRequest(BaseModel):
    user_id: str
    test_id: str
    answers: Dict[str, Any]
    score: Optional[float] = 0
    metadata: Optional[Dict[str, Any]] = None

class RegisterRequest(BaseModel):
    user_id: str
    test_id: str

@router.post("/save")
async def save_attempt(
    payload: SaveAttemptRequest,
    db: Client = Depends(get_db)
):
    try:
        response = db.table("user_tests").insert({
            "user_id": payload.user_id,
            "test_id": payload.test_id,
            "answers": payload.answers,
            "score": payload.score,
            "metadata": payload.metadata
        }).execute()
        
        # In v2, insert returns APIResponse. .data contains array of inserted rows.
        if response.data:
            return {"data": response.data[0], "error": None}
        return {"data": None, "error": "Insert failed"}
    except Exception as e:
        print(f"Error saving attempt: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/user/{user_id}")
async def get_user_attempts(
    user_id: str,
    request: Request,
    db: Client = Depends(get_db)
):
    print(f"\n{'='*60}")
    print(f"GET /attempts/user/{user_id} - REQUEST RECEIVED")
    print(f"{'='*60}")
    
    try:
        # 1. Security Check: Explicitly verify the JWT token
        auth_header = request.headers.get("Authorization")
        print(f"Auth Header Present: {bool(auth_header)}")
        
        if not auth_header:
             raise HTTPException(status_code=401, detail="Missing Authorization header")
        
        token = auth_header.replace("Bearer ", "")
        user_response = db.auth.get_user(token)
        
        if not user_response or not user_response.user:
             raise HTTPException(status_code=401, detail="Invalid token")
        
        # Check if requesting user is admin or the user themselves
        requesting_user_id = user_response.user.id
        requesting_user_email = user_response.user.email
        print(f"Requesting User ID: {requesting_user_id}")
        print(f"Requesting User Email: {requesting_user_email}")
        print(f"Target User ID: {user_id}")
        
        # Fetch requesting user's admin status from 'admins' table
        from app.core.database import supabase
        admin_res = supabase.table("admins").select("email").eq("email", requesting_user_email).execute()
        is_admin = admin_res.data and len(admin_res.data) > 0
        print(f"Is Admin: {is_admin}")
        
        # Allow if admin OR if viewing own data
        if not is_admin and requesting_user_id != user_id:
             raise HTTPException(status_code=403, detail="Not authorized to view this history")

        # 2. Use Admin Client with Application-Side Join (Bypass Missing FK)

        # Step A: Fetch attempts using global supabase client (Service Role) to bypass RLS
        # This allows admins to view any user's attempts
        print(f"\nFetching attempts from user_tests table...")
        attempts_res = supabase.table("user_tests")\
            .select("id, test_id, score, created_at, answers")\
            .eq("user_id", user_id)\
            .order("created_at", desc=True)\
            .execute()
        
        print(f"Attempts Query Response: {attempts_res}")
        print(f"Attempts Data: {attempts_res.data}")
        print(f"Number of attempts found: {len(attempts_res.data) if attempts_res.data else 0}")
            
        attempts_data = attempts_res.data or []
        
        if not attempts_data:
            print("No attempts found - returning empty array")
            return []

        # Step B: Fetch related Test Details
        test_ids = list(set([a["test_id"] for a in attempts_data if a.get("test_id")]))
        print(f"\nTest IDs to fetch: {test_ids}")
        
        tests_map = {}
        if test_ids:
            try:
                # Use global 'supabase' client (likely Service Role) to fetch tests
                # This ensures we get details even if the test is private/unlisted
                tests_res = supabase.table("tests")\
                    .select("id, title, questions, settings")\
                    .in_("id", test_ids)\
                    .execute()
                
                print(f"Tests fetched: {len(tests_res.data) if tests_res.data else 0}")
                
                if tests_res.data:
                    tests_map = {t["id"]: t for t in tests_res.data}
            except Exception as e:
                print(f"Error fetching related tests: {e}")
                # Degrade gracefully - return attempts without enriched data

        # Step C: Merge Data
        enriched = []
        for item in attempts_data:
            tid = item.get("test_id")
            test = tests_map.get(tid)
            
            if not test:
                 flat = {
                    "id": item["id"],
                    "test_id": tid,
                    "score": item["score"],
                    "created_at": item["created_at"],
                    "answers": item["answers"],
                    "test_title": "Deleted Test",
                    "test_questions": [], 
                    "test_settings": {} 
                }
            else:
                flat = {
                    "id": item["id"],
                    "test_id": tid,
                    "score": item["score"],
                    "created_at": item["created_at"],
                    "answers": item["answers"],
                    "test_title": test.get("title") or "Unknown Test",
                    # Include questions for detailed view
                    "test_questions": test.get("questions") or [],
                    "test_settings": test.get("settings") or {} 
                }
            enriched.append(flat)
        
        print(f"\nFinal enriched attempts count: {len(enriched)}")
        print(f"Returning: {enriched}")
        print(f"{'='*60}\n")
            
        return enriched
        
    except Exception as e:
        print(f"!!! ERROR in get_user_attempts: {e}")
        import traceback
        traceback.print_exc()
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/check/{user_id}/{test_id}")
async def check_attempt_status(
    user_id: str,
    test_id: str,
    db: Client = Depends(get_db)
):
    try:
        # 1. Check registrations
        reg_res = db.table("test_registrations")\
            .select("id")\
            .eq("user_id", user_id)\
            .eq("test_id", test_id)\
            .limit(1)\
            .execute()
            
        has_attempted = False
        if reg_res.data and len(reg_res.data) > 0:
            has_attempted = True
        else:
             # 2. Check user_tests
            att_res = db.table("user_tests")\
                .select("id")\
                .eq("user_id", user_id)\
                .eq("test_id", test_id)\
                .limit(1)\
                .execute()
            if att_res.data and len(att_res.data) > 0:
                has_attempted = True
                
        return {"hasAttempted": has_attempted}

    except Exception as e:
        print(f"Error checking attempt status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/register")
async def register_start(
    payload: RegisterRequest,
    db: Client = Depends(get_db)
):
    try:
        # Check existing
        existing = db.table("test_registrations")\
            .select("id")\
            .eq("user_id", payload.user_id)\
            .eq("test_id", payload.test_id)\
            .execute()
            
        if existing.data:
            return {"success": True}
            
        response = db.table("test_registrations").insert({
            "user_id": payload.user_id,
            "test_id": payload.test_id
        }).execute()
        
        return {"success": True}
        
    except Exception as e:
        print(f"Error registering start: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/test/{test_id}")
async def get_test_attempts(
    test_id: str,
    db: Client = Depends(get_db)
):
    try:
        # Fetch all attempts for specific test
        response = db.table("user_tests")\
            .select("*")\
            .eq("test_id", test_id)\
            .order("score", desc=True)\
            .execute()
        return response.data
    except Exception as e:
        print(f"Error fetching test attempts: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{attempt_id}")
async def delete_attempt(
    attempt_id: str,
    db: Client = Depends(get_db)
):
    try:
        db.table("user_tests").delete().eq("id", attempt_id).execute()
        return {"success": True}
    except Exception as e:
        print(f"Error deleting attempt: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/registration/{test_id}/{user_id}")
async def delete_registration(
    test_id: str,
    user_id: str,
    db: Client = Depends(get_db)
):
    try:
        db.table("test_registrations").delete().eq("test_id", test_id).eq("user_id", user_id).execute()
        return {"success": True}
    except Exception as e:
        print(f"Error deleting registration: {e}")
        raise HTTPException(status_code=500, detail=str(e))
