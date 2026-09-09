from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, get_session
from app.models.user import User
from app.schemas.backup import BackupPayload
from app.services.backup_service import build_backup, restore_backup

router = APIRouter(prefix="/backup", tags=["backup"])

# SECURITY (stopgap, temporary): backup_service.py is not yet user-aware —
# export_backup dumps every user's data across the whole instance into one
# JSON blob, and import_backup wipes and replaces every core table for
# every user before restoring only what's in the uploaded payload. Until a
# later plan adds per-user backup scoping (Part 3), both routes are
# restricted to admins so that an ordinary (or unauthenticated) caller
# can't read or destroy every other user's data. Do NOT remove this gate
# without first making backup_service.py user-aware.


@router.get("/export", response_model=BackupPayload)
async def export_backup(
    session: AsyncSession = Depends(get_session), _admin: User = Depends(get_current_admin)
) -> BackupPayload:
    return await build_backup(session)


@router.post("/import")
async def import_backup(
    payload: BackupPayload,
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(get_current_admin),
) -> dict[str, str]:
    await restore_backup(session, payload)
    return {"status": "ok"}
