from fastapi import APIRouter, HTTPException, Depends
from app.core.database import get_db
from supabase import Client
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

router = APIRouter()

class CategoryCreate(BaseModel):
    name: str

class CategoryUpdate(BaseModel):
    name: str

class TestCategoryAssignment(BaseModel):
    category_ids: List[str]

@router.get("/")
async def get_categories(db: Client = Depends(get_db)):
    try:
        response = db.table("categories").select("*").order("name").execute()
        return response.data
    except Exception as e:
        print(f"Error fetching categories: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/")
async def create_category(payload: CategoryCreate, db: Client = Depends(get_db)):
    try:
        response = db.table("categories").insert({"name": payload.name}).execute()
        if response.data:
            return response.data[0]
        return None
    except Exception as e:
        error_str = str(e)
        if "duplicate key" in error_str or "23505" in error_str:
             raise HTTPException(status_code=409, detail="Category already exists")
        print(f"Error creating category: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{category_id}")
async def update_category(category_id: str, payload: CategoryUpdate, db: Client = Depends(get_db)):
    try:
        response = db.table("categories").update({"name": payload.name}).eq("id", category_id).execute()
        if response.data:
            return response.data[0]
        return None
    except Exception as e:
        print(f"Error updating category: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{category_id}")
async def delete_category(category_id: str, db: Client = Depends(get_db)):
    try:
        response = db.table("categories").delete().eq("id", category_id).execute()
        return {"success": True}
    except Exception as e:
        print(f"Error deleting category: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stats")
async def get_category_stats(db: Client = Depends(get_db)):
    try:
        # Fetch all categories
        cats_res = db.table("categories").select("id, name, created_at").order("name").execute()
        cats = cats_res.data
        
        # Fetch test_categories mappings (all)
        # Note: If this table is huge, this is inefficient. Ideally use a View or RPC.
        # But for now, acceptable.
        map_res = db.table("test_categories").select("category_id").execute()
        mapping = map_res.data
        
        # Count
        counts = {}
        for m in mapping:
            cid = m["category_id"]
            counts[cid] = counts.get(cid, 0) + 1
            
        # Enrich
        enriched = []
        for c in cats:
            enriched.append({
                **c,
                "count": counts.get(c["id"], 0)
            })
            
        return enriched
        
    except Exception as e:
         print(f"Error fetching category stats: {e}")
         raise HTTPException(status_code=500, detail=str(e))

@router.get("/test/{test_id}")
async def get_test_categories(test_id: str, db: Client = Depends(get_db)):
    try:
        response = db.table("test_categories").select("category_id").eq("test_id", test_id).execute()
        # Return list of IDs
        return [item["category_id"] for item in response.data] if response.data else []
    except Exception as e:
        print(f"Error fetching test categories: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/assign/{test_id}")
async def assign_categories(test_id: str, payload: TestCategoryAssignment, db: Client = Depends(get_db)):
    try:
        # 1. Delete existing
        db.table("test_categories").delete().eq("test_id", test_id).execute()
        
        # 2. Insert new
        if payload.category_ids:
            rows = [{"test_id": test_id, "category_id": cid} for cid in payload.category_ids]
            db.table("test_categories").insert(rows).execute()
            
        return {"success": True}
    except Exception as e:
        print(f"Error assigning categories: {e}")
        raise HTTPException(status_code=500, detail=str(e))
