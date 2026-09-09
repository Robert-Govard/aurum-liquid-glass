from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.settings import AppSettings


async def get_or_create_app_settings(session: AsyncSession, user_id: int | None = None) -> AppSettings:
    """One row per user — get-or-create so callers never hit a missing
    row even if registration's seeding hasn't run for some reason (e.g. a
    row manually deleted). In normal operation this row is created once,
    at registration (see db/seed.py:seed_default_app_settings, called from
    services/auth_service.py:register).

    `user_id` is optional only as a bridge for callers that haven't been
    converted to per-user scoping yet — today that's exclusively
    crypto_service.py's three call sites, which have no `user_id` at all
    since crypto routes don't sit behind get_current_user (crypto is
    entirely out of scope for this multi-tenant migration's Part 1; see
    that plan's "Next Plans" section for Part 2, which converts crypto).
    When `user_id` is None, this falls back to the lowest-id existing row
    (deterministic, but arbitrary — there's no real "the" settings row
    anymore now that settings are per-user), or creates one with no owner
    if none exists at all. This is a temporary bridge for
    crypto_service.py's not-yet-converted calls. Remove this branch once
    Part 2 makes crypto per-user too and threads a real user_id through
    here like every other caller already does."""
    if user_id is not None:
        result = await session.execute(select(AppSettings).where(AppSettings.user_id == user_id))
        settings = result.scalar_one_or_none()
        if settings is None:
            settings = AppSettings(user_id=user_id)
            session.add(settings)
            await session.commit()
            await session.refresh(settings)
        return settings

    # Legacy, not-yet-per-user fallback (crypto_service.py only — see
    # docstring above). Grabs the lowest-id existing row rather than
    # scoping by owner, since there's no caller identity to scope by here.
    # ORDER BY is required for determinism: with many rows now (one per
    # user), an unordered LIMIT 1 can return a different row across
    # requests since Postgres makes no ordering guarantee without it.
    result = await session.execute(select(AppSettings).order_by(AppSettings.id).limit(1))
    settings = result.scalar_one_or_none()
    if settings is None:
        settings = AppSettings()
        session.add(settings)
        await session.commit()
        await session.refresh(settings)
    return settings
