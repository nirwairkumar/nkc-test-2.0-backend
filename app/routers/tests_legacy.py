from fastapi import APIRouter, HTTPException, Depends, Query
from app.core.database import get_db
from supabase import Client
from typing import Optional, List, Dict, Any
from pydantic import BaseModel

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




@router.get("/all")
async def get_all_tests(db: Client = Depends(get_db)):
    try:
        response = db.table("tests").select("*").order("created_at", desc=True).execute()
        return response.data
    except Exception as e:
        print(f"Error fetching all tests: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/feed")
async def get_tests_feed(
    page: int = Query(1, ge=1),
    limit: int = Query(12, ge=1, le=100),
    search_query: Optional[str] = None,
    category_id: Optional[str] = None,
    db: Client = Depends(get_db)
):
    try:
        # Pre-filter by category if needed
        category_test_ids = None
        if category_id:
             tc_res = db.table("test_categories").select("test_id").eq("category_id", category_id).execute()
             if not tc_res.data:
                 # No tests in this category
                 return {
                    "tests": [],
                    "meta": {"page": page, "has_more": False}
                }
             category_test_ids = [item["test_id"] for item in tc_res.data]

        # 1. Calculate Pagination
        start = (page - 1) * limit
        end = start + limit - 1

        # 2. Build Query
        query = db.table("tests")\
            .select("*, classes(name)")\
            .eq("is_public", True)\
            .order("created_at", desc=True)

        if category_test_ids is not None:
             query = query.in_("id", category_test_ids)

        if search_query:
            # Search Title or Custom ID
            # formatting for supabase rpc or client or_: "column.operator.value,column.operator.value"
            cleaned_query = search_query.replace(",", "") # prevent injection/breakage in filter string
            query = query.or_(f"title.ilike.%{cleaned_query}%,custom_id.ilike.%{cleaned_query}%")

        # 3. Execute Query
        tests_res = query.range(start, end).execute()
        tests = tests_res.data

        if not tests:
             return {
                "tests": [],
                "meta": {
                    "page": page,
                    "has_more": False
                }
            }

        # 4. Extract IDs for Batch Fetching
        test_ids = [t["id"] for t in tests]
        creator_ids = list(set([t["created_by"] for t in tests if t.get("created_by")]))

        # 5. Fetch Categories (map test_id -> category names/ids)
        # Fetch test_categories mapping
        # We need a way to get categories for these tests. 
        # Supabase doesn't support deep nested join easily in one go for M2M often without proper setup.
        # Let's do it in two steps as Frontend did.
        
        # Determine all categories needed
        test_cats_res = db.table("test_categories").select("*").in_("test_id", test_ids).execute()
        test_cats = test_cats_res.data
        
        category_ids = list(set([tc["category_id"] for tc in test_cats]))
        
        # Fetch actual Category objects
        cats_res = db.table("categories").select("*").in_("id", category_ids).execute()
        all_cats = {c["id"]: c for c in cats_res.data} # Access by ID
        
        # Build Map: test_id -> [Category Objects]
        tests_categories_map = {}
        for tc in test_cats:
            tid = tc["test_id"]
            cid = tc["category_id"]
            if tid not in tests_categories_map:
                tests_categories_map[tid] = []
            if cid in all_cats:
                tests_categories_map[tid].append(all_cats[cid])

        # 6. Fetch Verified Creators
        verified_creators = {}
        if creator_ids:
            creators_res = db.table("profiles").select("id, is_verified_creator, full_name, avatar_url").in_("id", creator_ids).execute()
            for c in creators_res.data:
                verified_creators[c["id"]] = {
                    "is_verified": c.get("is_verified_creator", False),
                    "name": c.get("full_name"),
                    "avatar": c.get("avatar_url")
                }

        # 7. Enrich Test Objects (Optional: or return side-by-side)
        # To match frontend expectation "data" usually is just list of tests, 
        # but we want to return enriched data. 
        # Let's attach metadata to the tests or return a composite object.
        # The frontend `fetchTests` expected `{ data, error }`.
        # We will return the new structure and update frontend to handle it.
        
        typesafe_tests = []
        for t in tests:
            # Inject creator info if we have it (to save frontend lookup)
            cid = t.get("created_by")
            if cid and cid in verified_creators:
                t["creator_name"] = verified_creators[cid]["name"]
                t["creator_avatar"] = verified_creators[cid]["avatar"]
                t["creator_verified"] = verified_creators[cid]["is_verified"]
            
            # Inject Categories
            t["categories"] = tests_categories_map.get(t["id"], [])
            
            typesafe_tests.append(t)

        return {
            "tests": typesafe_tests,
            "meta": {
                "page": page,
                "has_more": len(tests) == limit
            }
        }

    except Exception as e:
        print(f"Error fetching test feed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/user/{user_id}")
async def get_user_tests(
    user_id: str,
    db: Client = Depends(get_db)
):
    try:
        # Fetch tests created by user
        tests_res = db.table("tests")\
            .select("*, classes(name), test_likes(count)")\
            .eq("created_by", user_id)\
            .order("created_at", desc=True)\
            .execute()
        
        tests = tests_res.data
        if not tests:
            return []

        # Enrich with categories (Similar logic to feed)
        test_ids = [t["id"] for t in tests]
        
        test_cats_res = db.table("test_categories").select("*").in_("test_id", test_ids).execute()
        test_cats = test_cats_res.data
        
        category_ids = list(set([tc["category_id"] for tc in test_cats]))
        cats_res = db.table("categories").select("*").in_("id", category_ids).execute()
        all_cats = {c["id"]: c for c in cats_res.data}
        
        tests_categories_map = {}
        for tc in test_cats:
            tid = tc["test_id"]
            cid = tc["category_id"]
            if tid not in tests_categories_map:
                tests_categories_map[tid] = []
            if cid in all_cats:
                tests_categories_map[tid].append(all_cats[cid])

        # Fetch Creator Info (User themselves)
        profile_res = db.table("profiles").select("id, is_verified_creator, full_name, avatar_url").eq("id", user_id).single().execute()
        creator_info = profile_res.data if profile_res.data else {}
        
        enriched_tests = []
        for t in tests:
            # Inject Categories
            t["categories"] = tests_categories_map.get(t["id"], [])
            # Inject Creator Info
            if creator_info:
                t["creator_name"] = creator_info.get("full_name")
                t["creator_avatar"] = creator_info.get("avatar_url")
                t["creator_verified"] = creator_info.get("is_verified_creator")
            
            enriched_tests.append(t)
            
        return enriched_tests

    except Exception as e:
        print(f"Error fetching user tests: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{test_id}")
async def get_test_by_id(
    test_id: str,
    db: Client = Depends(get_db)
):
    try:
        # Check if UUID
        import uuid
        is_uuid = False
        try:
            uuid.UUID(test_id)
            is_uuid = True
        except ValueError:
            is_uuid = False
            
        # Fetch test based on ID type
        if is_uuid:
            test_res = db.table("tests").select("*, classes(name)").eq("id", test_id).execute()
        else:
            # Try custom_id first
            test_res = db.table("tests").select("*, classes(name)").eq("custom_id", test_id).execute()
            
            # If not found, try slug
            if not test_res.data:
                test_res = db.table("tests").select("*, classes(name)").eq("slug", test_id).execute()
        
        # Handle response
        if not test_res.data or len(test_res.data) == 0:
            raise HTTPException(status_code=404, detail="Test not found")
        
        test = test_res.data[0]  # Get first result

        # Enrich with Creator Info
        if test.get("created_by"):
            creator_res = db.table("profiles").select("id, is_verified_creator, full_name, avatar_url").eq("id", test["created_by"]).execute()
            if creator_res.data:
                c = creator_res.data[0]
                test["creator_name"] = c.get("full_name")
                test["creator_avatar"] = c.get("avatar_url")
                test["creator_verified"] = c.get("is_verified_creator")

        # Enrich with Categories
        test_cats_res = db.table("test_categories").select("category_id").eq("test_id", test["id"]).execute()
        if test_cats_res.data:
            cat_ids = [tc["category_id"] for tc in test_cats_res.data]
            cats_res = db.table("categories").select("*").in_("id", cat_ids).execute()
            test["categories"] = cats_res.data or []
        else:
            test["categories"] = []

        return test

    except Exception as e:
        print(f"Error fetching test details: {e}")
        # Supabase specific error handling could be better but broad catch for now
        raise HTTPException(status_code=404, detail="Test not found")


@router.get("/slug/{slug}")
async def get_test_by_slug(
    slug: str,
    db: Client = Depends(get_db)
):
    try:
        # Fetch Test by Slug
        query = db.table("tests").select("*, classes(name)").eq("slug", slug).single()
        test_res = query.execute()
        test = test_res.data
        
        if not test:
            raise HTTPException(status_code=404, detail="Test not found")

        # Enrich with Creator Info
        if test.get("created_by"):
            creator_res = db.table("profiles").select("id, is_verified_creator, full_name, avatar_url").eq("id", test["created_by"]).single().execute()
            if creator_res.data:
                c = creator_res.data
                test["creator_name"] = c.get("full_name")
                test["creator_avatar"] = c.get("avatar_url")
                test["creator_verified"] = c.get("is_verified_creator")

        # Enrich with Categories
        test_cats_res = db.table("test_categories").select("category_id").eq("test_id", test["id"]).execute()
        if test_cats_res.data:
            cat_ids = [tc["category_id"] for tc in test_cats_res.data]
            cats_res = db.table("categories").select("*").in_("id", cat_ids).execute()
            test["categories"] = cats_res.data or []
        else:
            test["categories"] = []

        return test

    except Exception as e:
        print(f"Error fetching test by slug: {e}")
        raise HTTPException(status_code=404, detail="Test not found")

# --- DTOs ---

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


# --- Admin / Management Endpoints ---

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
            
        data = response.data
        if data and len(data) > 0:
            last_id = data[0]["custom_id"]
            # Extract number
            if last_id and last_id.startswith(prefix):
                 num_part = last_id[len(prefix):]
                 if num_part.isdigit():
                     next_num = int(num_part) + 1
                     return {"next_id": f"{prefix}{str(next_num).zfill(3)}"}
        
        # Default start
        return {"next_id": f"{prefix}001"}

    except Exception as e:
        print(f"Error generating next ID: {e}")
        # Fallback random? No, return error or stable default
        return {"next_id": f"{prefix}001"}

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
            return response.data[0] if response.data else None
        except Exception as e:
            # If schema mismatch (missing columns for new features), retry with safe legacy fields
            print(f"Full insert failed (likely schema mismatch or syntax): {e}. Retrying with legacy fields only.")
            
            # Define fields that differ between old and new schema
            # We keep only the fields we are 100% sure exist in the 'old' version
            legacy_keys = {
                "title", "description", "questions", "created_by", "created_at", 
                "custom_id", "duration", "marks_per_question", "negative_marks", 
                "is_public", "visibility", "revision_notes", "institution_name",
                "institution_logo", "slug", "tags", "class_id", "sections", "test_id"
            }
            # Also creator_name/avatar might be missing if that migration wasn't run
            # But let's try to keep them if possible, or fall back further? 
            # For strict safety, let's include them in the 'legacy' set only if user confirmed, 
            # but user said 'deployed works' -> deployed likely has basic fields.
            
            safe_data = {k: v for k, v in data.items() if k in legacy_keys}
            
            # Try insert again
            response = db.table("tests").insert(safe_data).execute()
            print("Legacy insert successful.")
            return response.data[0] if response.data else None
    except Exception as e:
        print(f"Error creating test: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{test_id}")
async def update_test(test_id: str, payload: Dict[str, Any], db: Client = Depends(get_db)):
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
