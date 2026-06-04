"""dev_seed.py — local-dev / e2e bootstrap: create the SQLite schema and seed a dev user.

Not part of the app or the unit-test suite. Run once against a fresh SQLite file
(both local dev and the Playwright e2e harness use it):

    BETWISE_TEST_DB_URL="sqlite+aiosqlite:///./e2e.sqlite" python -m backend.dev_seed

Idempotent: re-running won't duplicate the dev user or the sample tables. The dev
user id matches BETWISE_DEV_USER_ID / VITE_DEV_USER_ID so the auth bypass resolves
to a real row. chip_balance is intentionally omitted so the seed tracks the
User.chip_balance column default rather than hard-coding a starting bankroll.
"""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import select

from backend.database import Base, get_engine, get_session_factory
from backend.models import CasinoTable, User

DEV_USER_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


async def main() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = get_session_factory()
    async with factory() as session:
        existing = await session.get(User, DEV_USER_ID)
        if existing is None:
            session.add(User(id=DEV_USER_ID, username="dev"))

        result = await session.scalars(select(CasinoTable))
        if not result.first():
            session.add(CasinoTable(name="Beginner Table", min_bet=500, max_bet=10_000, max_seats=3))
            session.add(CasinoTable(name="High Roller", min_bet=5_000, max_bet=50_000, max_seats=3))

        await session.commit()
    print("dev_seed: schema created, dev user + sample tables ensured.")


if __name__ == "__main__":
    asyncio.run(main())
