from supabase import create_client

# Read environment variables
SUPABASE_URL = "https://ajxtouqthtdenhqcvdft.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFqeHRvdXF0aHRkZW5ocWN2ZGZ0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjUyODM2ODMsImV4cCI6MjA4MDg1OTY4M30.ZNLxxidHNmMNAWKpb-MnKyEY9hHolrgDEVNOChNG3vM"

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
