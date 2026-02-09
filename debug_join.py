
from dotenv import load_dotenv
import os
from supabase import create_client, Client

load_dotenv(dotenv_path="d:\\Yuga Yatra\\nkc-Test-platform\\backend\\.env")
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

print("--- Testing Join ---")
try:
    # 1. Simple select to ensure rows exist (ignoring output count for now, just checking errors)
    print("Attempting Simple Select...")
    r1 = supabase.table("user_tests").select("id, test_id").limit(1).execute()
    print("Simple Select OK. Rows:", len(r1.data))

    # 2. Join Select
    print("Attempting Join Select...")
    r2 = supabase.table("user_tests").select("id, test_id, tests(title)").limit(1).execute()
    print("Join Select OK. Rows:", len(r2.data))
    if r2.data:
        print("Sample:", r2.data[0])

except Exception as e:
    print(f"FAILED: {e}")
