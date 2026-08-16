from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.schemas.backup import BackupPayload
from app.services.backup_service import build_backup, restore_backup

router = APIRouter(prefix="/backup", tags=["backup"])


@router.get("/export", response_model=BackupPayload)
async def export_backup(session: AsyncSession = Depends(get_session)) -> BackupPayload:
    return await build_backup(session)


@router.post("/import")
async def import_backup(payload: BackupPayload, session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    await restore_backup(session, payload)
    return {"status": "ok"}
