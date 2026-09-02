from fastapi import APIRouter, HTTPException
from models.predict import PredictRequest
from services.moderation import ModerationService
from errors import BusinessLogicError

router = APIRouter(tags=["moderation"])

@router.post("/predict", response_model=bool)
async def predict(payload: PredictRequest) -> bool:
    try:
        service = ModerationService()
        return service.predict(payload)
    except BusinessLogicError as e:
        raise HTTPException(status_code=500, detail=str(e))