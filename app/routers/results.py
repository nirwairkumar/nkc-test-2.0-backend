from fastapi import APIRouter, HTTPException, Depends
from app.core.database import get_db
from supabase import Client
from typing import Optional, Dict, Any, List

router = APIRouter()

@router.get("/{attempt_id}")
async def get_test_result(
    attempt_id: str,
    db: Client = Depends(get_db)
):
    try:
        # Fetch attempt with test details
        response = db.table("user_tests")\
            .select("*, tests(*, profiles(full_name, avatar_url))")\
            .eq("id", attempt_id)\
            .execute()
            
        if not response.data:
            raise HTTPException(status_code=404, detail="Result not found")
            
        result = response.data[0]
        test = result.get("tests")
        
        # We can perform additional server-side calculations here if needed
        # e.g., Rank calculation (mocked or real)
        
        # Rank logic (expensive, so maybe simple query counting scores higher than this)
        # count_higher = db.table("user_tests").select("id", count="exact").eq("test_id", result["test_id"]).gt("score", result["score"]).execute()
        # rank = count_higher.count + 1
        
        return {
            "attempt": result,
            "test": test,
            "analytics": {
                # "rank": rank,
                "percentile": 0 # Placeholder
            }
        }

    except Exception as e:
        print(f"Error fetching result: {e}")
        raise HTTPException(status_code=500, detail=str(e))
