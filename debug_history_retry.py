
from dotenv import load_dotenv
import os
from supabase import create_client, Client

load_dotenv(dotenv_path="d:\\Yuga Yatra\\nkc-Test-platform\\backend\\.env")

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")

if not url:
    print("FATAL: SUPABASE_URL not found.")
    exit(1)

supabase: Client = create_client(url, key)

print("--- Checking 'user_tests' table ---")
try:
    res = supabase.table("user_tests").select("*").limit(1).execute()
    print("SUCCESS: 'user_tests' table exists!")
    if res.data:
        print("Columns:", res.data[0].keys())
    else:
        print("Table is empty, but exists.")
except Exception as e:
    print(f"FAILED: 'user_tests' check failed: {e}")
