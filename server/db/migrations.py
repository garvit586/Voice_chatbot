"""Forward-only SQL migrations — runs every .sql file in migrations/ once."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import asyncpg  # type: ignore[import-untyped]

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


async def run_migrations(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS _migration (
                id SERIAL PRIMARY KEY,
                filename TEXT NOT NULL UNIQUE,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        applied: set[str] = {
            r["filename"] for r in await conn.fetch("SELECT filename FROM _migration")
        }
        files = sorted(MIGRATIONS_DIR.glob("*.sql"))
        for f in files:
            if f.name in applied:
                continue
            sql = f.read_text()
            await conn.execute(sql)
            await conn.execute(
                "INSERT INTO _migration(filename) VALUES($1)", f.name
            )
            print(f"  applied {f.name}")


async def _main() -> None:
    dsn = os.environ.get("DATABASE_URL", "postgresql://vchat:vchat@localhost:5433/vchat")
    pool = await asyncpg.create_pool(dsn)
    await run_migrations(pool)
    await pool.close()
    print("migrations done")


if __name__ == "__main__":
    asyncio.run(_main())
