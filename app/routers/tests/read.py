from fastapi import APIRouter, HTTPException, Depends, Query
from app.core.database import get_db
from supabase import Client
from typing import Optional, List, Dict, Any
from app.routers.tests.schemas import *
import uuid

router = APIRouter()

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

        # 7. Enrich Test Objects
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
