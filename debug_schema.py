
import asyncio
import os
from dotenv import load_dotenv
from supabase import create_client, Client

# Load env from .env file
load_dotenv()

# We need to manually set these if loading from .env fails or isn't set up in this script context
# But likely it will pick up processing .env
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("Error: SUPABASE_URL or SUPABASE_KEY not found in environment")
    exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def check_schema():
    print(f"Checking schema for table 'tests' at {SUPABASE_URL}...")
    
    try:
        # Assuming we can access information_schema via postgrest? 
        # Often Supabase works, but sometimes it's restricted.
        # Let's try to just select one row from tests and see keys if info schema fails
        
        # Method 1: information_schema (best if allowed)
        # Note: 'rpc' might be needed if direct select on system tables is blocked
        # But let's try direct select.
        
        # Using a raw SQL query via rpc is ideal if we had one, but we don't.
        # We can try to select * limit 1 and print keys.
        
        response = supabase.table("tests").select("*").limit(1).execute()
        if response.data:
            print("Columns found in 'tests' table (based on select *):")
            print(list(response.data[0].keys()))
        else:
            print("Table 'tests' is empty, cannot infer columns from select *.")
            print("Attempting insert of dummy data to test columns...")
            
    except Exception as e:
        print(f"Error querying tests: {e}")

if __name__ == "__main__":
    check_schema()
