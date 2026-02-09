
from dotenv import load_dotenv
import os
from supabase import create_client, Client

load_dotenv()

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

print("--- Checking 'materials' table for 'class_id' ---")
try:
    # Try selecting class_id
    res = supabase.table("materials").select("class_id").limit(1).execute()
    print("SUCCESS: 'class_id' column exists.")
except Exception as e:
    print(f"FAILURE: 'class_id' column check failed: {e}")

print("\n--- Checking Storage Buckets ---")
try:
    buckets = supabase.storage.list_buckets()
    bucket_names = [b.name for b in buckets]
    print(f"Buckets found: {bucket_names}")
    if "materials" in bucket_names:
        print("SUCCESS: 'materials' bucket exists.")
    else:
        print("FAILURE: 'materials' bucket MISSING.")
except Exception as e:
    print(f"Error checking buckets: {e}")
