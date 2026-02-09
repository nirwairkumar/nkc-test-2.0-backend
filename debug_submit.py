
from dotenv import load_dotenv
import os
from supabase import create_client, Client

# Explicit path to ensure it loads
load_dotenv(dotenv_path="d:\\Yuga Yatra\\nkc-Test-platform\\backend\\.env")

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")

print(f"URL: {url}")
# print(f"Key: {key}") # Don't print key
if not url:
    print("FATAL: SUPABASE_URL not found.")
    exit(1)

supabase: Client = create_client(url, key)

print("--- Simulating Test Submission ---")
# 1. Get a valid user
try:
    print("Fetching user...")
    user_res = supabase.table("profiles").select("id").limit(1).execute()
    if not user_res.data:
        print("No users found in profiles.")
        exit(1)
    user_id = user_res.data[0]['id']
    print(f"Using User ID: {user_id}")
except Exception as e:
    print(f"Failed to get user: {e}")
    exit(1)

# 2. Get a valid test
try:
    print("Fetching test...")
    test_res = supabase.table("tests").select("id").limit(1).execute()
    if not test_res.data:
        print("No tests found.")
        exit(1)
    test_id = test_res.data[0]['id']
    print(f"Using Test ID: {test_id}")
except Exception as e:
    print(f"Failed to get test: {e}")
    exit(1)

# 3. Attempt Insert
data = {
    "user_id": user_id,
    "test_id": test_id,
    "answers": {"1": "A"},
    "marks_scored": 10,
    "total_marks": 100,
    "metadata": {"source": "debug_script"},
    "student_name": "Debug User",
    "test_name": "Debug Test"
}

print(f"Inserting data...")

try:
    res = supabase.table("test_results").insert(data).execute()
    print("SUCCESS! Inserted:", res.data)
except Exception as e:
    print(f"INSERT FAILED: {e}")
