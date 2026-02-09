import asyncio
import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_KEY")
supabase: Client = create_client(url, key)

async def test_fetch(test_id):
    print(f"Testing fetch for ID: {test_id}")
    
    try:
        # Replicating logic from routers/tests.py
        query = supabase.table("tests").select("*").single()
        
        is_uuid = False
        try:
            import uuid
            uuid.UUID(test_id)
            is_uuid = True
        except ValueError:
            is_uuid = False
            
        if is_uuid:
            print("Identified as UUID")
            query = query.eq("id", test_id)
        else:
            print("Identified as Custom ID / Slug")
            # Logic in production:
            # query = query.or_(f"custom_id.eq.{test_id},slug.eq.{test_id}")
            # Let's test this exactly
            query = query.or_(f"custom_id.eq.{test_id},slug.eq.{test_id}")
            
        test_res = query.execute()
        print(f"Result Data: {test_res.data}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    # Test with a known ID (Replace with one you think exists, e.g. YT-240)
    # If uncertain, we can list first 5 tests to find a valid custom_id
    
    try:
        print("Listing first 5 tests to find valid IDs...")
        res = supabase.table("tests").select("id, custom_id, slug").limit(5).execute()
        for t in res.data:
            print(t)
            
        if res.data:
            target = res.data[0].get('custom_id') or res.data[0].get('slug')
            if target:
                asyncio.run(test_fetch(target))
            else:
                print("No custom_id or slug found in first 5 tests. Testing random string.")
                asyncio.run(test_fetch("YT-240"))
    except Exception as e:
        print(f"Setup Error: {e}")
