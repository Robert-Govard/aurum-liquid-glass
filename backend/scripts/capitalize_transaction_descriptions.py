"""One-off backfill: capitalizes the first letter of every existing
transaction/recurring-template description, so historical rows entered with
mixed casing ("покупка продуктов", "ПОКУПКА хлеба") match the auto-
capitalization now applied on create/update (see app/core/text.py and the
description validators in app/schemas/transaction.py, app/schemas/recurring.py).

Run it once against a running stack with:

    docker compose exec backend python -m scripts.capitalize_transaction_descriptions

Safe to re-run — already-capitalized descriptions are left untouched.
"""
import asyncio

from sqlalchemy import select

from app.core.text import capitalize_first_letter
from app.db.session import AsyncSessionLocal
from app.models import RecurringTransaction, Transaction


async def _capitalize_all(session, model) -> int:
    result = await session.execute(select(model))
    updated = 0
    for row in result.scalars().all():
        fixed = capitalize_first_letter(row.description)
        if fixed != row.description:
            row.description = fixed
            updated += 1
    return updated


async def main() -> None:
    async with AsyncSessionLocal() as session:
        transactions_updated = await _capitalize_all(session, Transaction)
        recurring_updated = await _capitalize_all(session, RecurringTransaction)
        await session.commit()
        print(f"Transactions updated: {transactions_updated}")
        print(f"Recurring templates updated: {recurring_updated}")


if __name__ == "__main__":
    asyncio.run(main())
