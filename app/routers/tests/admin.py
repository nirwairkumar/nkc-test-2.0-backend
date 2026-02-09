from fastapi import APIRouter, HTTPException, Depends, Query
from app.core.database import get_db
from supabase import Client

router = APIRouter()

@router.get("/all")
async def get_all_tests(
    db: Client = Depends(get_db)
):
    try:
        # Fetch ALL tests (for admin)
        response = db.table("tests").select("*, classes(name)").order("created_at", desc=True).execute()
        return response.data
    except Exception as e:
        print(f"Error fetching all tests: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/next-id")
async def get_next_test_id(
    prefix: str = Query("M", regex="^(M|YT)$"),
    db: Client = Depends(get_db)
):
    try:
        # Fetch latest ID with prefix
        # We want custom_id like 'M001' or 'YT005'
        # Supabase doesn't support complex regex in 'like' easily, so we use ilike 'prefix%' and order desc
        response = db.table("tests")\
            .select("custom_id")\
            .ilike("custom_id", f"{prefix}%")\
            .order("custom_id", desc=True)\
            .limit(1)\
            .execute()
        
        last_id_str = response.data[0]["custom_id"] if response.data else None
        
        if not last_id_str:
             return {"next_id": f"{prefix}001"}
        
        # Parse number
        try:
            # Assuming format prefix + 3 digits
            num_part = last_id_str[len(prefix):]
            next_num = int(num_part) + 1
            return {"next_id": f"{prefix}{next_num:03d}"}
        except ValueError:
             # Fallback if format is weird
             return {"next_id": f"{prefix}001"}

    except Exception as e:
        print(f"Error fetching next ID: {e}")
        # Default fallback
        return {"next_id": f"{prefix}001"}
