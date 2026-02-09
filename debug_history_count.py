
from dotenv import load_dotenv
import os
from supabase import create_client, Client

load_dotenv(dotenv_path="d:\\Yuga Yatra\\nkc-Test-platform\\backend\\.env")
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

print("--- Counting user_tests ---")
try:
    res = supabase.table("user_tests").select("id", count="exact").execute()
    print(f"Total rows in user_tests: {res.count}")
    
    if res.count == 0:
        print("Table is empty. This explains why history is empty.")
    else:
        print("Table has data. Fetching sample...")
        print(res.data[:1])

except Exception as e:
    print(f"Count failed: {e}")
