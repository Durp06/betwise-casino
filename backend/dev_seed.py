"""dev_seed.py — local-dev only: create the sqlite schema and seed a dev user.

Not part of the app or the test suite. Run once against a fresh dev.sqlite:

    $env:BETWISE_TEST_DB_URL="sqlite+aiosqlite:///./dev.sqlite"
    backend/.venv/Scripts/python.exe -m backend.dev_seed

Idempotent: re-running won't duplicate the dev user or the sample tables.
"""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import select

from backend.database import Base, get_engine, get_session_factory
from backend.models import CasinoTable, STARTING_BALANCE_CENTS, User

DEV_USER_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


async def main() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = get_session_factory()
    async with factory() as session:
        existing = await session.get(User, DEV_USER_ID)
        if existing is None:
            session.add(User(id=DEV_USER_ID, username="dev", chip_balance=STARTING_BALANCE_CENTS))

        result = await session.scalars(select(CasinoTable))
        if not result.first():
            session.add(CasinoTable(name="Beginner Table", min_bet=500, max_bet=10_000, max_seats=3))
            session.add(CasinoTable(name="High Roller", min_bet=5_000, max_bet=50_000, max_seats=3))

        await session.commit()
    print("dev_seed: schema created, dev user + sample tables ensured.")


if __name__ == "__main__":
    asyncio.run(main())
