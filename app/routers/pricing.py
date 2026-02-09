from fastapi import APIRouter, HTTPException, Depends
from app.core.database import get_db
from supabase import Client
from typing import Optional, List, Any, Dict
from pydantic import BaseModel

router = APIRouter()

# --- Schemas ---

class PlanCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    price: int # paise
    duration_days: int
    features: List[str] = []
    is_active: bool = True

class PromoCodeCreate(BaseModel):
    code: str
    type: str # 'flat' or 'percentage'
    value: int
    max_discount: Optional[int] = None
    min_order_value: int = 0
    max_uses: Optional[int] = None
    valid_from: str
    valid_till: Optional[str] = None
    is_active: bool = True

# --- Plans Endpoints ---

@router.get("/plans")
async def get_plans(db: Client = Depends(get_db)):
    try:
        response = db.table("plans").select("*").order("price", desc=False).execute()
        return response.data
    except Exception as e:
        print(f"Error fetching plans: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/plans")
async def create_plan(payload: PlanCreate, db: Client = Depends(get_db)):
    try:
        data = payload.dict(exclude_unset=True)
        response = db.table("plans").insert(data).select().single().execute()
        return response.data
    except Exception as e:
        print(f"Error creating plan: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/plans/{plan_id}")
async def update_plan(plan_id: str, payload: Dict[str, Any], db: Client = Depends(get_db)):
    try:
        response = db.table("plans").update(payload).eq("id", plan_id).execute()
        if response.data:
            return response.data[0]
        return None
    except Exception as e:
        print(f"Error updating plan: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/plans/{plan_id}")
async def delete_plan(plan_id: str, db: Client = Depends(get_db)):
    try:
        response = db.table("plans").delete().eq("id", plan_id).execute()
        return {"success": True}
    except Exception as e:
        print(f"Error deleting plan: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- Promo Codes Endpoints ---

@router.get("/promos")
async def get_promos(db: Client = Depends(get_db)):
    try:
        response = db.table("promo_codes").select("*").order("created_at", desc=False).execute()
        return response.data
    except Exception as e:
        print(f"Error fetching promos: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/promos")
async def create_promo(payload: PromoCodeCreate, db: Client = Depends(get_db)):
    try:
        data = payload.dict(exclude_unset=True)
        response = db.table("promo_codes").insert(data).select().single().execute()
        return response.data
    except Exception as e:
        print(f"Error creating promo: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/promos/{promo_id}")
async def update_promo(promo_id: str, payload: Dict[str, Any], db: Client = Depends(get_db)):
    try:
        response = db.table("promo_codes").update(payload).eq("id", promo_id).execute()
        if response.data:
            return response.data[0]
        return None
    except Exception as e:
        print(f"Error updating promo: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/promos/{promo_id}")
async def delete_promo(promo_id: str, db: Client = Depends(get_db)):
    try:
        response = db.table("promo_codes").delete().eq("id", promo_id).execute()
        return {"success": True}
    except Exception as e:
        print(f"Error deleting promo: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class ApplyPromoRequest(BaseModel):
    code: str
    plan_id: str

@router.post("/promos/apply")
async def apply_promo(payload: ApplyPromoRequest, db: Client = Depends(get_db)):
    try:
        code = payload.code.upper()
        # Fetch Promo
        promo_res = db.table("promo_codes").select("*").eq("code", code).eq("is_active", True).execute()
        if not promo_res.data:
            raise HTTPException(status_code=400, detail="Invalid or inactive promo code")
        
        promo = promo_res.data[0]
        
        # Check Validity Dates
        import datetime
        now = datetime.datetime.now().isoformat()
        if promo.get("valid_from") and promo["valid_from"] > now:
             raise HTTPException(status_code=400, detail="Promo code not yet valid")
        if promo.get("valid_till") and promo["valid_till"] < now:
             raise HTTPException(status_code=400, detail="Promo code expired")
             
        # Check Usage Limits
        if promo.get("max_uses") is not None:
            if promo.get("used_count", 0) >= promo["max_uses"]:
                raise HTTPException(status_code=400, detail="Promo code usage limit reached")

        # Fetch Plan
        plan_res = db.table("plans").select("*").eq("id", payload.plan_id).single().execute()
        if not plan_res.data:
            raise HTTPException(status_code=404, detail="Plan not found")
        
        plan_price = plan_res.data["price"]
        
        # Check Min Order Value
        if promo.get("min_order_value", 0) > plan_price:
             raise HTTPException(status_code=400, detail=f"Minimum order value of {promo['min_order_value']/100} required")

        # Calculate Discount
        discount = 0
        if promo["type"] == "flat":
            discount = promo["value"]
        elif promo["type"] == "percentage":
            discount = int(plan_price * (promo["value"] / 100))
            if promo.get("max_discount"):
                discount = min(discount, promo["max_discount"])
        
        final_price = max(0, plan_price - discount)
        
        return {
            "code": code,
            "discount": discount,
            "finalPrice": final_price,
            "originalPrice": plan_price
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Error applying promo: {e}")
        raise HTTPException(status_code=500, detail=str(e))
