from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.settings import AppSettings


async def get_or_create_app_settings(session: AsyncSession, user_id: int) -> AppSettings:
    """One row per user — get-or-create so callers never hit a missing
    row even if registration's seeding hasn't run for some reason (e.g. a
    row manually deleted). In normal operation this row is created once,
    at registration (see db/seed.py:seed_default_app_settings, called from
    services/auth_service.py:register).

    `user_id` used to be optional, as a legacy bridge for callers that
    predated per-user scoping: when it was None, this fell back to the
    lowest-id existing row (ORDER BY was required there for determinism,
    since an unordered LIMIT 1 has no guaranteed order once there are many
    per-user rows), or created an ownerless row if none existed yet.
    crypto_service.py's three call sites were the last ones relying on
    that fallback (from before crypto routes sat behind get_current_user);
    once they were converted to pass a real user_id, no call site depended
    on the None path anymore, and the final multi-tenant NOT NULL cutover
    on AppSettings.user_id (see the make_user_id_not_null migration) made
    an ownerless row invalid at the schema level too — so the fallback
    branch was removed and `user_id` became a required argument, per this
    docstring's own earlier note to do so once nothing referenced it."""
    result = await session.execute(select(AppSettings).where(AppSettings.user_id == user_id))
    settings = result.scalar_one_or_none()
    if settings is None:
        settings = AppSettings(user_id=user_id)
        session.add(settings)
        await session.commit()
        await session.refresh(settings)
    return settings
