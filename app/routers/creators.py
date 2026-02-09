from fastapi import APIRouter, HTTPException, Depends
from app.core.database import get_db
from supabase import Client

router = APIRouter()

@router.get("/{creator_id}")
async def get_creator_profile(creator_id: str, db: Client = Depends(get_db)):
    try:
        # 1. Fetch Profile
        profile_res = db.table("profiles").select("*").eq("id", creator_id).single().execute()
        if not profile_res.data:
            raise HTTPException(status_code=404, detail="Creator not found")
        
        # 2. Fetch Public Tests
        # Note: In frontend it was: .select('*, classes(name), test_categories(category_id)')
        tests_res = db.table("tests")\
            .select("*, classes(name), test_categories(category_id)")\
            .eq("created_by", creator_id)\
            .eq("visibility", "public")\
            .execute()
            
        # 3. Fetch Classes
        # Frontend: fetchClasses(creatorId) -> db.from('classes').select('*').eq('user_id', creatorId)
        classes_res = db.table("classes").select("*").eq("user_id", creator_id).execute()

        # 4. Fetch Materials
        # Frontend: fetchMaterials(creatorId) -> db.from('materials').select('*, classes(name)').eq('user_id', creatorId)
        materials_res = db.table("materials").select("*, classes(name)").eq("user_id", creator_id).execute()
        
        return {
            "profile": profile_res.data,
            "tests": tests_res.data,
            "classes": classes_res.data,
            "materials": materials_res.data
        }

    except Exception as e:
        print(f"Error fetching creator profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))
