from fastapi import APIRouter
from app.routers.tests import read, write, admin

router = APIRouter()

# Include sub-routers
# Order matters! Specific paths must come before wildcards (/{id}).

# Admin routes (/all, /next-id)
router.include_router(admin.router)

# Write routes (Create /, Update /{id}, Delete /{id}, Debug /debug/schema)
# Note: PUT/DELETE don't conflict with GET. 
# But /debug/schema (GET) needs to be matched before /{test_id} (GET) in read.
router.include_router(write.router)

# Read routes (/feed, /{id}, /slug/{slug}, /user/{id})
# /{id} is a catch-all for GET, so it must be last.
router.include_router(read.router)
