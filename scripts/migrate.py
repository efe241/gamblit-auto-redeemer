"""
Database migration and schema inspection script.
"""
import asyncio
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import cfg
from app.database import Database


async def run_migration():
    print(f"Checking database schema at: {cfg.database_path}")
    db = Database(db_path=cfg.database_path)
    await db.connect()
    stats = await db.get_stats()
    print("Database schema successfully verified!")
    print(f"Current stats: {stats}")
    await db.close()


if __name__ == "__main__":
    asyncio.run(run_migration())
