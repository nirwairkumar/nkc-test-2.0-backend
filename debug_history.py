
from dotenv import load_dotenv
import os
from supabase import create_client, Client

load_dotenv()

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

print("--- Checking 'user_tests' table ---")
try:
    res = supabase.table("user_tests").select("id, test_id, score").limit(1).execute()
    print("Basic Select Success:", res.data)
except Exception as e:
    print(f"Basic Select Failed: {e}")

print("\n--- Checking Join user_tests -> tests ---")
try:
    # Try the exact query from attempts.py
    # We need a user_id that actually has attempts. I'll remove the .eq('user_id') filter to just check if the syntax works for ANY row.
    res = supabase.table("user_tests")\
            .select("id, test_id, tests(title)")\
            .limit(1)\
            .execute()
    print("Join Success:", res.data)
except Exception as e:
    print(f"Join Failed: {e}")
