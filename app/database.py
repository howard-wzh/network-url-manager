import os
import aiosqlite
from datetime import datetime, timezone
from typing import Optional

DB_PATH = os.environ.get("DB_PATH", "./data/urls.db")


async def init_db() -> None:
    db_dir = os.path.dirname(os.path.abspath(DB_PATH))
    os.makedirs(db_dir, exist_ok=True)

    async with aiosqlite.connect(DB_PATH) as db:
        # ── migrate old backup_urls (single URL with UNIQUE → multi-URL list) ──
        async with db.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='backup_urls'"
        ) as cur:
            row = await cur.fetchone()
            if row and "UNIQUE" in (row[0] or ""):
                await db.execute("DROP TABLE backup_urls")

        # ── core tables ────────────────────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS backup_urls (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                environment TEXT    NOT NULL,
                currency    TEXT    NOT NULL,
                field       TEXT    NOT NULL,
                url         TEXT    NOT NULL,
                note        TEXT    NOT NULL DEFAULT '',
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
                new_url     TEXT    NOT NULL,
                note        TEXT    NOT NULL DEFAULT ''
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT    UNIQUE NOT NULL,
                password_hash TEXT    NOT NULL,
                role          TEXT    NOT NULL DEFAULT 'readonly'
            )
        """)

        # ── migrations: add columns to existing tables if missing ──────────────
        for stmt in (
            "ALTER TABLE backup_urls ADD COLUMN note TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE deploy_history ADD COLUMN note TEXT NOT NULL DEFAULT ''",
        ):
            try:
                await db.execute(stmt)
            except Exception:
                pass  # column already exists

        await db.commit()

    # ── init admin user from env vars ──────────────────────────────────────────
    admin_user = os.environ.get("ADMIN_USER", "").strip()
    admin_pass = os.environ.get("ADMIN_PASS", "").strip()
    if admin_user and admin_pass:
        await _ensure_admin(admin_user, admin_pass)


async def _ensure_admin(username: str, password: str) -> None:
    """Create admin user if not exists; upgrade role if exists but not admin."""
    from .auth import hash_password
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, role FROM users WHERE username=?", (username,)
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            await db.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?,?,?)",
                (username, hash_password(password), "admin"),
            )
        elif row[1] != "admin":
            await db.execute(
                "UPDATE users SET role='admin' WHERE id=?", (row[0],)
            )
        await db.commit()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── users ──────────────────────────────────────────────────────────────────────

async def get_user_by_username(username: str) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, username, password_hash, role FROM users WHERE username=?",
            (username,),
        ) as cur:
            row = await cur.fetchone()
    if row is None:
        return None
    return {"id": row[0], "username": row[1], "password_hash": row[2], "role": row[3]}


async def get_all_users() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, username, role FROM users ORDER BY id"
        ) as cur:
            rows = await cur.fetchall()
    return [{"id": r[0], "username": r[1], "role": r[2]} for r in rows]


async def create_user(username: str, password_hash: str, role: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?,?,?)",
            (username, password_hash, role),
        )
        await db.commit()
        return cur.lastrowid


async def update_user(
    user_id: int, username: str, password_hash: Optional[str], role: str
) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        if password_hash:
            await db.execute(
                "UPDATE users SET username=?, password_hash=?, role=? WHERE id=?",
                (username, password_hash, role, user_id),
            )
        else:
            await db.execute(
                "UPDATE users SET username=?, role=? WHERE id=?",
                (username, role, user_id),
            )
        await db.commit()


async def delete_user(user_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM users WHERE id=?", (user_id,))
        await db.commit()


# ── backup_urls (multi-URL list per cell) ──────────────────────────────────────

async def get_all_backup_urls() -> dict:
    """Return nested dict env → currency → field → [{id, url, note}, ...]."""
    result: dict = {}
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, environment, currency, field, url, note FROM backup_urls ORDER BY created_at ASC"
        ) as cur:
            for row_id, env, currency, field, url, note in await cur.fetchall():
                lst = result.setdefault(env, {}).setdefault(currency, {}).setdefault(field, [])
                lst.append({"id": row_id, "url": url, "note": note or ""})
    return result


async def add_backup_url(
    env: str, currency: str, field: str, url: str, note: str = ""
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO backup_urls (environment, currency, field, url, note, created_at) VALUES (?,?,?,?,?,?)",
            (env, currency, field, url, note, _now()),
        )
        await db.commit()
        return cur.lastrowid


async def update_backup_url(backup_id: int, url: str, note: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE backup_urls SET url=?, note=? WHERE id=?",
            (url, note, backup_id),
        )
        await db.commit()


async def get_backup_note(backup_id: int) -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT note FROM backup_urls WHERE id=?", (backup_id,)
        ) as cur:
            row = await cur.fetchone()
    return row[0] if row else ""


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
    note: str = "",
) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO deploy_history
                (timestamp, operator, environment, currency, field, old_url, new_url, note)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            (_now(), operator, env, currency, field, old_url, new_url, note),
        )
        await db.commit()


async def get_deploy_history(limit: int = 100) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT timestamp, operator, environment, currency, field, old_url, new_url, note
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
            "note":        r[7] or "",
        }
        for r in rows
    ]


async def get_using_notes() -> dict:
    """Return latest deploy note per env/currency/field (only non-empty notes)."""
    result: dict = {}
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT environment, currency, field, note
            FROM deploy_history
            WHERE id IN (
                SELECT MAX(id) FROM deploy_history
                GROUP BY environment, currency, field
            )
            AND note IS NOT NULL AND note != ''
            """
        ) as cur:
            for env, currency, field, note in await cur.fetchall():
                result.setdefault(env, {}).setdefault(currency, {})[field] = note
    return result
