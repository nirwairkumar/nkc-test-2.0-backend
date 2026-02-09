import os
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "NKC Test Platform API"
    PROJECT_VERSION: str = "1.0.0"
    
    # API Configuration
    API_V1_STR: str = "/api/v1"
    
    # Supabase Configuration
    SUPABASE_URL: str
    SUPABASE_URL: str
    SUPABASE_KEY: str  # Anon Key
    SUPABASE_SERVICE_KEY: Optional[str] = None # Service Role Key for Admin Access
    
    # AI Config
    GEMINI_API_KEY: Optional[str] = None
    
    # Security
    SECRET_KEY: str = "YOUR_SUPER_SECRET_KEY_HERE_CHANGE_IN_PROD"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
