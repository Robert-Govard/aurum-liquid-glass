from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.models.user import User
from app.schemas.backup import BackupPayload
from app.services.backup_service import build_backup, restore_backup

router = APIRouter(prefix="/backup", tags=["backup"])

# SECURITY: backup_service.py (build_backup/restore_backup) is fully
# user-scoped — export_backup only ever reads the calling user's own rows,
# and restore_backup only ever deletes/replaces the calling user's own
# rows, stamping every restored row with that same user_id regardless of
# what (if anything) the uploaded payload implies. Both endpoints therefore
# only need an authenticated user, same as every other feature route — no
# admin gate is required or present here anymore.


@router.get("/export", response_model=BackupPayload)
async def export_backup(
    session: AsyncSession = Depends(get_session), current_user: User = Depends(get_current_user)
) -> BackupPayload:
    return await build_backup(session, current_user.id)


@router.post("/import")
async def import_backup(
    payload: BackupPayload,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    await restore_backup(session, payload, current_user.id)
    return {"status": "ok"}
