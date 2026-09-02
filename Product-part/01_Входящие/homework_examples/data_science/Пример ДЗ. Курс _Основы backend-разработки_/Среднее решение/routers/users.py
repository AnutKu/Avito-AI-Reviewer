from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field


router = APIRouter()


class PredictionRequest(BaseModel):
    seller_id: int = Field(..., ge=0)
    is_verified_seller: bool
    item_id: int = Field(..., ge=0)
    name: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    category: int = Field(..., ge=0)
    images_qty: int = Field(..., ge=0)


class PredictionResponse(BaseModel):
    is_valid: bool


@router.post("/predict", response_model=PredictionResponse)
async def predict(request: PredictionRequest):
    try:
        if request.is_verified_seller:
            is_valid = True
        else:
            is_valid = request.images_qty > 0
        
        return PredictionResponse(is_valid=is_valid)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
