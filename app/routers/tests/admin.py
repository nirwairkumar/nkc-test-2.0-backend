from fastapi import APIRouter, HTTPException, Depends, Query
from app.core.database import get_db
from supabase import Client

from typing import Optional, List, Dict, Any

router = APIRouter()

@router.get("/all")
async def get_all_tests(
    page: int = Query(1, ge=1),
    limit: int = Query(12, ge=1, le=100),
    search_query: Optional[str] = None,
    db: Client = Depends(get_db)
):
    try:
        # 1. Calculate Pagination
        start = (page - 1) * limit
        end = start + limit - 1

        # 2. Build Query
        if search_query:
            try:
                # RPC Search
                response = db.rpc("search_tests_ranked", {
                    "search_query": search_query,
                    "limit_val": limit,
                    "offset_val": start,
                    "is_admin": True # Ensures admin sees all visible relevant tests
                }).execute()
                tests = response.data
            except Exception as rpc_error:
                print(f"RPC Admin Search Error: {rpc_error}")
                # Fallback
                cleaned_query = search_query.replace(",", "")
                query = db.table("tests")\
                    .select("*, classes(name)")\
                    .order("created_at", desc=True)
                query = query.or_(f"title.ilike.%{cleaned_query}%,custom_id.ilike.%{cleaned_query}%")
                response = query.range(start, end).execute()
                tests = response.data
        else:
            query = db.table("tests")\
                .select("*, classes(name)")\
                .order("created_at", desc=True)
            response = query.range(start, end).execute()
            tests = response.data

        return {
            "tests": tests,
            "meta": {
                "page": page,
                "has_more": len(tests) == limit
            }
        }
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

@router.put("/admin/{test_id}")
async def admin_update_test(
    test_id: str,
    payload: Dict[str, Any],
):
    try:
        from app.core.database import supabase as admin_db
        # Update using Service Role Key (bypasses RLS)
        response = admin_db.table("tests").update(payload).eq("id", test_id).execute()
        return response.data[0] if response.data else None
    except Exception as e:
        print(f"Error updating test (admin): {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/admin/{test_id}")
async def admin_delete_test(
    test_id: str
):
    try:
        from app.core.database import supabase as admin_db
        # Delete using Service Role Key (bypasses RLS)
        response = admin_db.table("tests").delete().eq("id", test_id).execute()
        return {"success": True}
    except Exception as e:
        print(f"Error deleting test (admin): {e}")
        raise HTTPException(status_code=500, detail=str(e))
