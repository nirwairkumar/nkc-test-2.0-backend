from fastapi import APIRouter, HTTPException, Depends
from app.core.database import get_db
from supabase import Client
from pydantic import BaseModel
from typing import Optional, List

router = APIRouter()

# --- Schemas ---

class FollowRequest(BaseModel):
    follower_id: str
    following_id: str

class NotificationCreate(BaseModel):
    user_id: str
    title: str
    message: str
    link: Optional[str] = None
    custom_test_id: Optional[str] = None
    sender_name: Optional[str] = None
    sender_email: Optional[str] = None

# --- Follows ---

@router.post("/follows/follow")
async def follow_user(payload: FollowRequest, db: Client = Depends(get_db)):
    try:
        response = db.table("follows").insert(payload.dict()).execute()
        return response.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/follows/unfollow")
async def unfollow_user(payload: FollowRequest, db: Client = Depends(get_db)):
    try:
        response = db.table("follows").delete()\
            .eq("follower_id", payload.follower_id)\
            .eq("following_id", payload.following_id)\
            .execute()
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/follows/check")
async def check_follow(follower_id: str, following_id: str, db: Client = Depends(get_db)):
    try:
        response = db.table("follows").select("*")\
            .eq("follower_id", follower_id)\
            .eq("following_id", following_id)\
            .maybe_single().execute()
        return {"isFollowing": bool(response.data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/follows/stats/{user_id}")
async def get_follow_stats(user_id: str, db: Client = Depends(get_db)):
    try:
        followers = db.table("follows").select("*", count="exact").eq("following_id", user_id).execute()
        following = db.table("follows").select("*", count="exact").eq("follower_id", user_id).execute()
        return {
            "followers_count": followers.count,
            "following_count": following.count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/follows/followers/{user_id}")
async def get_followers(user_id: str, db: Client = Depends(get_db)):
    try:
        # Fetch followers of user_id
        response = db.table("follows").select("follower_id, created_at, follower:profiles!follows_follower_id_fkey(*)")\
            .eq("following_id", user_id)\
            .execute()
        return response.data
    except Exception as e:
        # Fallback if FK name issue?
        # print(e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/follows/following/{user_id}")
async def get_following(user_id: str, db: Client = Depends(get_db)):
    try:
        # Fetch who user_id is following
        response = db.table("follows").select("following_id, created_at, following:profiles!follows_following_id_fkey(*)")\
            .eq("follower_id", user_id)\
            .execute()
        return response.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Notifications ---

@router.get("/notifications/{user_id}")
async def get_notifications(user_id: str, limit: int = 50, db: Client = Depends(get_db)):
    try:
        response = db.table("notifications").select("*")\
            .eq("user_id", user_id)\
            .order("created_at", desc=True)\
            .limit(limit)\
            .execute()
        return response.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/notifications/create")
async def create_notification(payload: NotificationCreate, db: Client = Depends(get_db)):
    try:
        # payload.dict() works for simple inserts
        data = payload.dict(exclude_unset=True)
        response = db.table("notifications").insert(data).execute()
        return response.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/notifications/{id}/read")
async def mark_read(id: str, user_id: str, db: Client = Depends(get_db)):
    try:
        response = db.table("notifications").update({"read": True})\
            .eq("id", id)\
            .eq("user_id", user_id)\
            .execute()
        return response.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/notifications/{id}")
async def delete_notification(id: str, user_id: str, db: Client = Depends(get_db)):
    try:
        response = db.table("notifications").delete()\
            .eq("id", id)\
            .eq("user_id", user_id)\
            .execute()
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/notifications/clear/{user_id}")
async def clear_all_notifications(user_id: str, db: Client = Depends(get_db)):
    try:
        response = db.table("notifications").delete()\
            .eq("user_id", user_id)\
            .execute()
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
