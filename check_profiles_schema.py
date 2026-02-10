import os
from supabase import create_client
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

print("Checking profiles table structure...")
print("="*60)

try:
    # Try to select all columns from a single profile
    result = supabase.table("profiles").select("*").limit(1).execute()
    
    if result.data and len(result.data) > 0:
        print("✓ Profiles table exists")
        print(f"\nColumns found in profiles table:")
        print("-"*60)
        for key in result.data[0].keys():
            print(f"  - {key}")
        print("-"*60)
        
        # Check specifically for verification columns
        has_is_verified = 'is_verified_creator' in result.data[0]
        has_verified_at = 'verified_at' in result.data[0]
        
        print(f"\nVerification columns:")
        print(f"  is_verified_creator: {'✓ EXISTS' if has_is_verified else '✗ MISSING'}")
        print(f"  verified_at: {'✓ EXISTS' if has_verified_at else '✗ MISSING'}")
        
        if not has_is_verified or not has_verified_at:
            print("\n" + "="*60)
            print("⚠ VERIFICATION COLUMNS ARE MISSING!")
            print("="*60)
            print("\nYou need to run this SQL in Supabase SQL Editor:")
            print("""
ALTER TABLE public.profiles 
ADD COLUMN IF NOT EXISTS is_verified_creator BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS verified_role TEXT,
ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS verified_by_admin_id UUID REFERENCES auth.users(id);
""")
    else:
        print("✗ No profiles found in table")
        
except Exception as e:
    print(f"✗ Error: {e}")
