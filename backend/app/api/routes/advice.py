from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.models.user import User
from app.schemas.advice import AdviceResponse
from app.services.advice_service import get_advice

router = APIRouter(prefix="/advice", tags=["advice"])


@router.get("", response_model=AdviceResponse)
async def read_advice(
    session: AsyncSession = Depends(get_session), current_user: User = Depends(get_current_user)
) -> AdviceResponse:
    return await get_advice(session, current_user.id)
