import os
from dotenv import load_dotenv

# Load .env if present
load_dotenv()

# Read environment variables
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("Error: SUPABASE_URL or SUPABASE_KEY not set in environment.")
    exit(1)

# Create Supabase client
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

print("Checking if admins table exists and inserting admin email...")

try:
    # Try to insert directly into admins table
    result = supabase.table("admins").upsert({"email": "learnirwair@gmail.com"}, on_conflict="email").execute()
    print("✓ Admin email inserted/updated successfully!")
    print(f"Result: {result.data}")
except Exception as e:
    print(f"✗ Error: {e}")
    print("\n" + "="*60)
    print("MANUAL STEPS REQUIRED:")
    print("="*60)
    print("Please run this SQL in your Supabase SQL Editor:")
    print("""
CREATE TABLE IF NOT EXISTS public.admins (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO public.admins (email)
VALUES ('learnirwair@gmail.com')
ON CONFLICT (email) DO NOTHING;
""")
