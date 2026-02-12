import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_KEY")

if not url or not key:
    print("Error: Missing SUPABASE_URL or SUPABASE_KEY/SERVICE_KEY")
    exit(1)

supabase = create_client(url, key)

try:
    print("Fetching one row from 'admins' table...")
    response = supabase.table("admins").select("*").limit(1).execute()
    if response.data:
        print("Columns found:", list(response.data[0].keys()))
        print("Sample data:", response.data[0])
    else:
        print("Table 'admins' found but is empty. Cannot determine columns easily without data.")
        # Try to insert a dummy to fail and get error? No, safer to just ask or guess.
        print("Assuming 'email' column exists based on user description.")

except Exception as e:
    print(f"Error accessing 'admins' table: {e}")
