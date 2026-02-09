
from dotenv import load_dotenv
import os
from supabase import create_client, Client

load_dotenv()

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

print("--- Checking 'test_results' table ---")
try:
    res = supabase.table("test_results").select("*").limit(1).execute()
    print("Table 'test_results' exists.")
    if res.data:
        print("Columns:", res.data[0].keys())
    else:
        # If empty, we can't easily see keys from data, but at least we know it exists.
        print("Table is empty, checking if insert works or error message gives clues.")
except Exception as e:
    print(f"Error accessing 'test_results': {e}")
