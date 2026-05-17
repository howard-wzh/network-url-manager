import copy
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import database, gitlab_client
from .config import (
    AVAILABILITY, CURRENCIES, ENVIRONMENTS, FIELDS,
    FIELD_LABELS, FIELD_PATHS, FIELD_SOURCE,
    ENV_FILE_PATHS, DL_FILE_PATHS,
)

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.init_db()
    yield


app = FastAPI(title="URL Manager", lifespan=lifespan)


# ── helpers ────────────────────────────────────────────────────────────────────

def get_nested(data: dict, path: list[str]) -> Optional[str]:
    cur = data
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur if isinstance(cur, str) else None


def set_nested(data: dict, path: list[str], value: str) -> None:
    cur = data
    for key in path[:-1]:
        cur = cur.setdefault(key, {})
    cur[path[-1]] = value


# ── routes ─────────────────────────────────────────────────────────────────────

@app.get("/")
async def serve_index():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/api/data")
async def get_data():
    """Return using-URLs (live from GitLab), backup-URLs and expired-URLs (from SQLite)."""
    using_urls: dict = {}
    errors: dict = {}

    # Fetch all four JSON files, capturing individual failures
    gitlab_cache: dict[str, dict] = {}
    for env in ENVIRONMENTS:
        for kind, paths_map in [("env", ENV_FILE_PATHS), ("dl", DL_FILE_PATHS)]:
            key = f"{env}/{kind}"
            try:
                gitlab_cache[key] = await gitlab_client.get_file(paths_map[env])
            except Exception as exc:
                errors[key] = str(exc)

    for env in ENVIRONMENTS:
        using_urls[env] = {}
        env_json = gitlab_cache.get(f"{env}/env")
        dl_json  = gitlab_cache.get(f"{env}/dl")

        for currency in CURRENCIES:
            using_urls[env][currency] = {}
            for field in FIELDS:
                avail = AVAILABILITY[env][currency][field]
                if not avail:
                    using_urls[env][currency][field] = None
                    continue

                path = FIELD_PATHS[field].get(currency)
                if path is None:
                    using_urls[env][currency][field] = None
                    continue

                json_data = env_json if FIELD_SOURCE[field] == "env" else dl_json
                if json_data is None:
                    using_urls[env][currency][field] = None
                else:
                    using_urls[env][currency][field] = get_nested(json_data, path)

    backup_urls  = await database.get_all_backup_urls()
    expired_urls = await database.get_all_expired_urls()

    return {
        "using_urls":   using_urls,
        "backup_urls":  backup_urls,
        "expired_urls": expired_urls,
        "availability": AVAILABILITY,
        "errors":       errors or None,
    }


class BackupUrlRequest(BaseModel):
    environment: str
    currency: str
    field: str
    url: str


@app.put("/api/backup")
async def update_backup(req: BackupUrlRequest):
    """Persist a backup URL to SQLite (upsert). Send empty url to clear."""
    _validate(req.environment, req.currency, req.field)
    stripped = req.url.strip()
    if stripped:
        await database.set_backup_url(req.environment, req.currency, req.field, stripped)
    else:
        await database.delete_backup_url(req.environment, req.currency, req.field)
    return {"ok": True}


class DeployRequest(BaseModel):
    environment: str
    currency: str
    field: str
    backup_url: str
    username: str


@app.post("/api/deploy")
async def deploy(req: DeployRequest):
    """Push backup_url to GitLab, record the change, update SQLite."""
    _validate(req.environment, req.currency, req.field)

    if not AVAILABILITY[req.environment][req.currency][req.field]:
        raise HTTPException(400, "Field not available for this environment/currency")

    path = FIELD_PATHS[req.field].get(req.currency)
    if path is None:
        raise HTTPException(400, "No JSON path mapping for this field/currency")

    file_path = (
        ENV_FILE_PATHS[req.environment]
        if FIELD_SOURCE[req.field] == "env"
        else DL_FILE_PATHS[req.environment]
    )

    try:
        original = await gitlab_client.get_file(file_path)
    except Exception as exc:
        raise HTTPException(500, f"GitLab read failed: {exc}")

    old_url = get_nested(original, path)

    updated = copy.deepcopy(original)
    set_nested(updated, path, req.backup_url.strip())

    label = FIELD_LABELS.get(req.field, req.field)
    commit_msg = f"Update {label} {req.currency} URL by {req.username}"

    try:
        await gitlab_client.update_file(file_path, updated, commit_msg)
    except Exception as exc:
        raise HTTPException(500, f"GitLab push failed: {exc}")

    # Persist side-effects
    if old_url:
        await database.add_expired_url(req.environment, req.currency, req.field, old_url)
    await database.delete_backup_url(req.environment, req.currency, req.field)
    await database.add_deploy_history(
        req.username, req.environment, req.currency, req.field, old_url, req.backup_url.strip()
    )

    return {"ok": True, "old_url": old_url, "new_url": req.backup_url.strip()}


@app.get("/api/history")
async def get_history():
    return {"history": await database.get_deploy_history(100)}


# ── validation helper ──────────────────────────────────────────────────────────

def _validate(env: str, currency: str, field: str) -> None:
    if env not in ENVIRONMENTS:
        raise HTTPException(400, f"Unknown environment: {env}")
    if currency not in CURRENCIES:
        raise HTTPException(400, f"Unknown currency: {currency}")
    if field not in FIELDS:
        raise HTTPException(400, f"Unknown field: {field}")
