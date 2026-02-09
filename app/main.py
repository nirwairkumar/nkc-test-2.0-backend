from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.config import settings
from supabase import Client
from app.core.database import get_db
from pydantic import BaseModel

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION,
    openapi_url="/api/openapi.json",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# CORS Middleware
# In production, specific origins should be allowed.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For dev only
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), db: Client = Depends(get_db)):
    """
    Verifies the JWT token from Supabase Auth header.
    Authentication is handled by Supabase, but we verify the token's validity and identity here.
    """
    token = credentials.credentials
    try:
        user = db.auth.get_user(token)
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")
        return user.user
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

class UserLogin(BaseModel):
    email: str
    password: str
from app.routers import creators

app.include_router(creators.router, prefix="/api/creators", tags=["Creators"])

from app.routers import tests
app.include_router(tests.router, prefix="/api/tests", tags=["Tests"])

from app.routers import attempts
app.include_router(attempts.router, prefix="/api/attempts", tags=["Attempts"])

from app.routers import users
app.include_router(users.router, prefix="/api/users", tags=["Users"])

from app.routers import categories
app.include_router(categories.router, prefix="/api/categories", tags=["Categories"])

from app.routers import results
app.include_router(results.router, prefix="/api/results", tags=["Results"])

from app.routers import ai
app.include_router(ai.router, prefix="/api/ai", tags=["AI"])

from app.routers import classes

from app.routers import classes
app.include_router(classes.router, prefix="/api/classes", tags=["Classes"])

from app.routers import materials
app.include_router(materials.router, prefix="/api/materials", tags=["Materials"])

from app.routers import pricing
app.include_router(pricing.router, prefix="/api/pricing", tags=["Pricing"])

from app.routers import support
app.include_router(support.router, prefix="/api/support", tags=["Support"])

from app.routers import social
app.include_router(social.router, prefix="/api/social", tags=["Social"])

@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "project": settings.PROJECT_NAME,
        "version": settings.PROJECT_VERSION
    }

@app.post("/api/login")
def login(payload: UserLogin):
    """
    This endpoint is a placeholder. 
    The Frontend typically logs in directly with Supabase Client (JS), then sends the TOKEN to backend api.
    HOWEVER, if you want Backend-only logic:
    Frontend -> Backend -> Supabase Auth.
    
    Here strictly following the architecture request:
    'All backend logics should be separated and connected by api'
    So frontend will Call THIS endpoint with credentials, 
    This backend will call supabase.auth.sign_in_with_password
    """
    # This requires Supabase Service Key or Anon Key initialized client
    # We use a fresh client or the global one if configured for anon
    try:
        from app.core.database import supabase
        response = supabase.auth.sign_in_with_password({
            "email": payload.email,
            "password": payload.password
        })
        return response
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/me")
def read_users_me(user = Depends(get_current_user)):
    return user
