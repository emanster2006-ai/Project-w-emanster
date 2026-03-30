from fastapi import APIRouter
from pydantic import BaseModel
import time

router = APIRouter()

class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: float

@router.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="ok", version="1.0.0", timestamp=time.time())
