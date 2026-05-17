import os
import aiosqlite
from datetime import datetime, timezone
from typing import Optional

DB_PATH = os.environ.get("DB_PATH", "./data/urls.db")


async def init_db() -> None:
    db_dir = os.path.dirname(os.path.abspath(DB_PATH))
    os.makedirs(db_dir, exist_ok=True)

    async with aiosqlite.connect(DB_PATH) as db:
        # Migrate old backup_urls table (single URL with UNIQUE constraint → multi-URL list)
        async with db.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='backup_urls'"
        ) as cur:
            row = await cur.fetchone()
            if row and "UNIQUE" in (row[0] or ""):
                await db.execute("DROP TABLE backup_urls")

        await db.execute("""
            CREATE TABLE IF NOT EXISTS backup_urls (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                environment TEXT    NOT NULL,
                currency    TEXT    NOT NULL,
                field       TEXT    NOT NULL,
                url         TEXT    NOT NULL,
                created_at  TEXT    NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS expired_urls (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                environment TEXT    NOT NULL,
                currency    TEXT    NOT NULL,
                field       TEXT    NOT NULL,
                url         TEXT    NOT NULL,
                expired_at  TEXT    NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS deploy_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT    NOT NULL,
                operator    TEXT    NOT NULL,
                environment TEXT    NOT NULL,
                currency    TEXT    NOT NULL,
                field       TEXT    NOT NULL,
                old_url     TEXT,
                new_url     TEXT    NOT NULL
            )
        """)
        await db.commit()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── backup_urls (multi-URL list per cell) ──────────────────────────────────────

async def get_all_backup_urls() -> dict:
    """Return nested dict env → currency → field → [{id, url}, ...]."""
    result: dict = {}
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, environment, currency, field, url FROM backup_urls ORDER BY created_at ASC"
        ) as cur:
            for row_id, env, currency, field, url in await cur.fetchall():
                lst = result.setdefault(env, {}).setdefault(currency, {}).setdefault(field, [])
                lst.append({"id": row_id, "url": url})
    return result


async def add_backup_url(env: str, currency: str, field: str, url: str) -> int:
    """Add a backup URL to the list. Returns the new row id."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO backup_urls (environment, currency, field, url, created_at) VALUES (?,?,?,?,?)",
            (env, currency, field, url, _now()),
        )
        await db.commit()
        return cur.lastrowid


async def delete_backup_url_by_id(backup_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM backup_urls WHERE id=?", (backup_id,))
        await db.commit()


# ── expired_urls ───────────────────────────────────────────────────────────────

async def add_expired_url(env: str, currency: str, field: str, url: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO expired_urls (environment, currency, field, url, expired_at) VALUES (?,?,?,?,?)",
            (env, currency, field, url, _now()),
        )
        # Keep only the 2 most-recent expired URLs per cell
        await db.execute(
            """
            DELETE FROM expired_urls
            WHERE environment=? AND currency=? AND field=?
              AND id NOT IN (
                  SELECT id FROM expired_urls
                  WHERE environment=? AND currency=? AND field=?
                  ORDER BY expired_at DESC LIMIT 2
              )
            """,
            (env, currency, field, env, currency, field),
        )
        await db.commit()


async def get_all_expired_urls() -> dict:
    """Return nested dict env → currency → field → [url, ...] (max 2)."""
    bucket: dict[str, list[str]] = {}
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT environment, currency, field, url
            FROM expired_urls
            ORDER BY environment, currency, field, expired_at DESC
            """
        ) as cur:
            for env, currency, field, url in await cur.fetchall():
                key = f"{env}|{currency}|{field}"
                lst = bucket.setdefault(key, [])
                if len(lst) < 2:
                    lst.append(url)

    nested: dict = {}
    for key, urls in bucket.items():
        env, currency, field = key.split("|", 2)
        nested.setdefault(env, {}).setdefault(currency, {})[field] = urls
    return nested


# ── deploy_history ─────────────────────────────────────────────────────────────

async def add_deploy_history(
    operator: str,
    env: str,
    currency: str,
    field: str,
    old_url: Optional[str],
    new_url: str,
) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO deploy_history
                (timestamp, operator, environment, currency, field, old_url, new_url)
            VALUES (?,?,?,?,?,?,?)
            """,
            (_now(), operator, env, currency, field, old_url, new_url),
        )
        await db.commit()


async def get_deploy_history(limit: int = 100) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT timestamp, operator, environment, currency, field, old_url, new_url
            FROM deploy_history
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (limit,),
        ) as cur:
            rows = await cur.fetchall()
    return [
        {
            "timestamp":   r[0],
            "operator":    r[1],
            "environment": r[2],
            "currency":    r[3],
            "field":       r[4],
            "old_url":     r[5],
            "new_url":     r[6],
        }
        for r in rows
    ]
