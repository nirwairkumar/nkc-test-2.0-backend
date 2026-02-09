from supabase import create_client, Client
from app.core.config import settings
from fastapi import Request

# Global client (prefer Service Key for admin tasks)
key_to_use = settings.SUPABASE_SERVICE_KEY if settings.SUPABASE_SERVICE_KEY else settings.SUPABASE_KEY
supabase: Client = create_client(settings.SUPABASE_URL, key_to_use)

def get_db(request: Request = None):
    """
    Dependency to get the database client.
    """
    if request:
        auth_header = request.headers.get("Authorization")
        if auth_header:
            # Create client with Anon Key (standard for user context)
            client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
            client.options.headers.update({"Authorization": auth_header})
            
            # Note: For supabase-py v2, we might simply need to pass the header.
            # .auth() method usage depends on version.
            try:
                client.postgrest.auth(auth_header.replace("Bearer ", ""))
            except:
                pass 
            return client
    
    # Fallback to Admin/Global client
    return supabase
