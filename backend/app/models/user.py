"""A registered account. Every domain table (accounts, transactions, ...)
gets its own user_id FK pointing here (added in the follow-up "multi-tenant
data isolation" plan) — deleting a User cascades to all of it."""
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Flipped off by an admin (see routes/admin.py) to disable a login
    # without deleting the account or its data.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Set by auth_service.login()/verify_email() — register() no longer sets
    # this, since registering no longer logs the user in (email verification
    # is required first, see spec). NULL means "never logged in since this
    # column was added" for pre-existing users, or genuinely never
    # (registered but never came back). Not touched by auth_service.refresh()
    # — that's a silent session renewal, not an explicit login event.
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Verification state for the email the account was registered with —
    # see services/auth_service.py's register()/login()/verify_email().
    # Only one verification token is ever outstanding per user (unlike
    # refresh_tokens, which intentionally keeps many rows per user for
    # multiple devices), so this is three columns here rather than a
    # separate table: a new registration/resend just overwrites the
    # previous token's hash and expiry.
    is_email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    email_verification_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    email_verification_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Manually set/cleared by an admin via PATCH /admin/users/{id}/premium
    # (see routes/admin.py) — no payment gateway, no automation. NULL means
    # Free (never had Premium, or it was revoked/expired). A future
    # datetime means Premium until that moment. "Forever" is just a date
    # far in the future (the admin UI has a one-click "grant forever"
    # button for this) — no separate boolean, to avoid two fields that
    # could contradict each other about the same fact.
    premium_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def is_premium(self) -> bool:
        """True if this account currently has an active Premium
        subscription. Admins are always effectively Premium. This lives
        here (not only in services/plan_service.py) so that Pydantic's
        `from_attributes=True` conversion (see schemas/user.py's UserRead)
        picks it up automatically wherever a User ORM object is returned
        directly as a response — services/plan_service.py.is_premium() is
        still the canonical name the rest of the codebase should import
        and call; it just delegates to this property."""
        if self.is_admin:
            return True
        return self.premium_until is not None and self.premium_until > datetime.now(timezone.utc)
