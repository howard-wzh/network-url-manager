import copy
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

from . import database, gitlab_client
from .auth import (
    get_session_user, hash_password, require_admin,
    require_auth, require_rw, verify_password,
)
from .config import (
    AVAILABILITY, CURRENCIES, ENVIRONMENTS, FIELDS,
    FIELD_LABELS, FIELD_PATHS, FIELD_SOURCE,
    ENV_FILE_PATHS, DL_FILE_PATHS,
)

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.init_db()
    yield


app = FastAPI(title="URL Manager", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, max_age=None)


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


# ── pages ──────────────────────────────────────────────────────────────────────

@app.get("/")
async def serve_index(request: Request):
    if not get_session_user(request):
        return RedirectResponse(url="/login", status_code=302)
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/login")
async def serve_login(request: Request):
    if get_session_user(request):
        return RedirectResponse(url="/", status_code=302)
    return FileResponse(FRONTEND_DIR / "login.html")


# ── auth API ───────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


@app.post("/api/login")
async def api_login(req: LoginRequest, request: Request):
    user = await database.get_user_by_username(req.username.strip())
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="帳號或密碼錯誤")
    request.session["user"] = {
        "id":       user["id"],
        "username": user["username"],
        "role":     user["role"],
    }
    return {"ok": True, "username": user["username"], "role": user["role"]}


@app.post("/api/logout")
async def api_logout(request: Request):
    request.session.clear()
    return {"ok": True}


@app.get("/api/me")
async def api_me(user: dict = Depends(require_auth)):
    return {"username": user["username"], "role": user["role"]}


# ── data ───────────────────────────────────────────────────────────────────────

@app.get("/api/data")
async def get_data(user: dict = Depends(require_auth)):
    """Return using-URLs (live from GitLab), backup-URL lists and expired-URLs (from SQLite)."""
    using_urls: dict = {}
    errors: dict = {}

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
    using_notes  = await database.get_using_notes()

    return {
        "using_urls":   using_urls,
        "backup_urls":  backup_urls,
        "expired_urls": expired_urls,
        "using_notes":  using_notes,
        "availability": AVAILABILITY,
        "errors":       errors or None,
        "current_user": {"username": user["username"], "role": user["role"]},
    }


# ── backup URL list management ─────────────────────────────────────────────────

class AddBackupRequest(BaseModel):
    environment: str
    currency:    str
    field:       str
    url:         str
    note:        str = ""


@app.post("/api/backup")
async def add_backup(req: AddBackupRequest, _user: dict = Depends(require_rw)):
    _validate(req.environment, req.currency, req.field)
    url = req.url.strip()
    if not url:
        raise HTTPException(400, "URL cannot be empty")
    new_id = await database.add_backup_url(
        req.environment, req.currency, req.field, url, req.note.strip()
    )
    return {"ok": True, "id": new_id, "url": url, "note": req.note.strip()}


class UpdateBackupRequest(BaseModel):
    url:  str
    note: str = ""


@app.put("/api/backup/{backup_id}")
async def update_backup(
    backup_id: int, req: UpdateBackupRequest, _user: dict = Depends(require_rw)
):
    url = req.url.strip()
    if not url:
        raise HTTPException(400, "URL cannot be empty")
    await database.update_backup_url(backup_id, url, req.note.strip())
    return {"ok": True, "url": url, "note": req.note.strip()}


@app.delete("/api/backup/{backup_id}")
async def delete_backup(backup_id: int, _user: dict = Depends(require_rw)):
    await database.delete_backup_url_by_id(backup_id)
    return {"ok": True}


# ── deploy ─────────────────────────────────────────────────────────────────────

class DeployRequest(BaseModel):
    environment: str
    currency:    str
    field:       str
    backup_url:  str
    backup_id:   int


@app.post("/api/deploy")
async def deploy(req: DeployRequest, user: dict = Depends(require_rw)):
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

    # Fetch note before deleting the backup record
    backup_note = await database.get_backup_note(req.backup_id)

    try:
        original = await gitlab_client.get_file(file_path)
    except Exception as exc:
        raise HTTPException(500, f"GitLab read failed: {exc}")

    old_url  = get_nested(original, path)
    updated  = copy.deepcopy(original)
    set_nested(updated, path, req.backup_url.strip())

    label      = FIELD_LABELS.get(req.field, req.field)
    username   = user["username"]
    commit_msg = f"Update {label} {req.currency} URL by {username}"
    if backup_note:
        commit_msg += f" [{backup_note}]"

    try:
        await gitlab_client.update_file(file_path, updated, commit_msg)
    except Exception as exc:
        raise HTTPException(500, f"GitLab push failed: {exc}")

    await database.delete_backup_url_by_id(req.backup_id)

    if old_url:
        await database.add_expired_url(
            req.environment, req.currency, req.field, old_url
        )

    await database.add_deploy_history(
        username, req.environment, req.currency, req.field,
        old_url, req.backup_url.strip(), backup_note,
    )

    return {"ok": True, "old_url": old_url, "new_url": req.backup_url.strip()}


# ── history ────────────────────────────────────────────────────────────────────

@app.get("/api/history")
async def get_history(_user: dict = Depends(require_auth)):
    return {"history": await database.get_deploy_history(100)}


# ── user management (admin only) ───────────────────────────────────────────────

class CreateUserRequest(BaseModel):
    username: str
    password: str
    role:     str


class UpdateUserRequest(BaseModel):
    username: str
    password: Optional[str] = None
    role:     str


@app.get("/api/users")
async def list_users(_user: dict = Depends(require_admin)):
    return {"users": await database.get_all_users()}


@app.post("/api/users")
async def create_user(req: CreateUserRequest, _user: dict = Depends(require_admin)):
    if req.role not in ("readonly", "readwrite", "admin"):
        raise HTTPException(400, "Invalid role")
    if not req.username.strip() or not req.password:
        raise HTTPException(400, "Username and password required")
    try:
        uid = await database.create_user(
            req.username.strip(), hash_password(req.password), req.role
        )
        return {"ok": True, "id": uid}
    except Exception as exc:
        if "UNIQUE" in str(exc):
            raise HTTPException(409, "帳號已存在")
        raise HTTPException(500, str(exc))


@app.put("/api/users/{user_id}")
async def update_user_ep(
    user_id: int, req: UpdateUserRequest, user: dict = Depends(require_admin)
):
    if req.role not in ("readonly", "readwrite", "admin"):
        raise HTTPException(400, "Invalid role")
    if user_id == user["id"] and req.role != "admin":
        raise HTTPException(400, "無法取消自己的管理員權限")
    pw_hash = hash_password(req.password) if req.password else None
    await database.update_user(user_id, req.username.strip(), pw_hash, req.role)
    return {"ok": True}


@app.delete("/api/users/{user_id}")
async def delete_user_ep(user_id: int, user: dict = Depends(require_admin)):
    if user_id == user["id"]:
        raise HTTPException(400, "無法刪除自己的帳號")
    await database.delete_user(user_id)
    return {"ok": True}


# ── validation ─────────────────────────────────────────────────────────────────

def _validate(env: str, currency: str, field: str) -> None:
    if env not in ENVIRONMENTS:
        raise HTTPException(400, f"Unknown environment: {env}")
    if currency not in CURRENCIES:
        raise HTTPException(400, f"Unknown currency: {currency}")
    if field not in FIELDS:
        raise HTTPException(400, f"Unknown field: {field}")
