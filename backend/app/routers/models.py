from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import SupportedModel

router = APIRouter()


@router.get("")
async def list_models(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SupportedModel))
    models = result.scalars().all()
    return [
        {
            "id": m.id,
            "name": m.name,
            "framework": m.framework,
            "vram_required_gb": m.vram_required_gb,
            "price_base_units": str(m.price_base_units),
            "input_type": m.input_type,
            "supported_formats": m.supported_formats,
        }
        for m in models
    ]


@router.get("/{model_id}")
async def get_model(model_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SupportedModel).where(SupportedModel.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Model not found")
    return {
        "id": model.id,
        "name": model.name,
        "framework": model.framework,
        "vram_required_gb": model.vram_required_gb,
        "price_base_units": str(model.price_base_units),
        "input_type": model.input_type,
        "supported_formats": model.supported_formats,
        "max_input_size_mb": model.max_input_size_mb,
    }
