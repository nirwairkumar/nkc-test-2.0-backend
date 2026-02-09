@router.get("/all")
async def get_all_tests(db: Client = Depends(get_db)):
    try:
        response = db.table("tests").select("*").order("created_at", desc=True).execute()
        return response.data
    except Exception as e:
        print(f"Error fetching all tests: {e}")
        raise HTTPException(status_code=500, detail=str(e))
