
from dotenv import load_dotenv
import os
from supabase import create_client, Client

load_dotenv()

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

print("--- Probing 'test_results' columns ---")

def check_column(col):
    try:
        # Select specific column, limit 0 to just check validity
        supabase.table("test_results").select(col).limit(1).execute()
        print(f"[YES] Column '{col}' exists.")
        return True
    except Exception as e:
        # print(f"[NO]  Column '{col}' error: {e}")
        print(f"[NO]  Column '{col}' does NOT exist.")
        return False

check_column("user_id")
check_column("test_id")
check_column("answers")
check_column("score") # User has marks_scored, checking alias
check_column("marks_scored")
