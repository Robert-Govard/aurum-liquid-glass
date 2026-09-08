"""One-off helper to grant admin rights to an existing user by email.

Run it against a running stack with:

    docker compose exec backend python -m scripts.promote_admin someone@example.com

There's no self-service "become admin" path by design (open registration
with no invite codes means anyone could otherwise grant themselves admin)
— this is the only way to create the first admin account.
"""
import asyncio
import sys

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.user import User


async def promote(email: str) -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user is None:
            print(f"No user with email {email!r}")
            return
        user.is_admin = True
        await session.commit()
        print(f"{email} is now an admin")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m scripts.promote_admin <email>")
        sys.exit(1)
    asyncio.run(promote(sys.argv[1]))
