from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.settings import AppSettings


async def get_or_create_app_settings(session: AsyncSession, user_id: int | None = None) -> AppSettings:
    """One row per user — get-or-create so callers never hit a missing
    row even if registration's seeding hasn't run for some reason (e.g. a
    row manually deleted). In normal operation this row is created once,
    at registration (see db/seed.py:seed_default_app_settings, called from
    services/auth_service.py:register).

    `user_id` is optional only as a legacy bridge for callers that predate
    per-user scoping. As of Part 2 of the multi-tenant migration,
    crypto_service.py's three call sites (previously the only ones with no
    `user_id`, back when crypto routes didn't sit behind get_current_user)
    were converted to pass a real `user_id`, so this branch currently has
    NO remaining callers — every call site in the codebase now threads a
    real user_id through here. When `user_id` is None, this falls back to
    the lowest-id existing row (deterministic, but arbitrary — there's no
    real "the" settings row anymore now that settings are per-user), or
    creates one with no owner if none exists at all. The branch is being
    kept for now only because removing it is out of scope for this
    branch — it's a small, separate future cleanup, not urgent. Remove it
    once nothing references the `user_id=None` path anymore."""
    if user_id is not None:
        result = await session.execute(select(AppSettings).where(AppSettings.user_id == user_id))
        settings = result.scalar_one_or_none()
        if settings is None:
            settings = AppSettings(user_id=user_id)
            session.add(settings)
            await session.commit()
            await session.refresh(settings)
        return settings

    # Legacy fallback for the no-user_id case (see docstring above — as of
    # Part 2 of the multi-tenant migration, no call site actually hits this
    # branch anymore; kept only because removing it is a separate, small,
    # non-urgent future cleanup). Grabs the lowest-id existing row rather
    # than scoping by owner, since there's no caller identity to scope by here.
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
