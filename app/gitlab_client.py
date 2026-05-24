import base64
import json
import os
from urllib.parse import quote

import httpx

# All configurable via environment variables
GITLAB_BASE  = os.environ.get("GITLAB_URL",     "https://gitlab.com").rstrip("/")
_raw_project = os.environ.get("GITLAB_PROJECT",  "cheerstech/report/network-line-settings")
PROJECT_PATH = _raw_project.removesuffix(".git")   # strip .git suffix if present
BRANCH       = os.environ.get("GITLAB_BRANCH",   "master")

ENCODED_PROJECT = quote(PROJECT_PATH, safe="")


def _token() -> str:
    token = os.environ.get("GITLAB_TOKEN", "").strip()
    if not token:
        raise RuntimeError("GITLAB_TOKEN environment variable is not set")
    return token


def _file_url(file_path: str) -> str:
    return (
        f"{GITLAB_BASE}/api/v4/projects/{ENCODED_PROJECT}"
        f"/repository/files/{quote(file_path, safe='')}"
    )


async def get_file(file_path: str) -> dict:
    """Fetch *file_path* from GitLab and return its parsed JSON content."""
    async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
        resp = await client.get(
            _file_url(file_path),
            params={"ref": BRANCH},
            headers={"PRIVATE-TOKEN": _token()},
        )
        resp.raise_for_status()
        raw = base64.b64decode(resp.json()["content"])
        return json.loads(raw.decode("utf-8"))


async def update_file(file_path: str, content: dict, commit_message: str) -> None:
    """Overwrite *file_path* in GitLab with *content* and commit."""
    content_str = json.dumps(content, indent=2, ensure_ascii=False)
    async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
        resp = await client.put(
            _file_url(file_path),
            headers={
                "PRIVATE-TOKEN": _token(),
                "Content-Type": "application/json",
            },
            json={
                "branch": BRANCH,
                "content": content_str,
                "commit_message": commit_message,
                "encoding": "text",
            },
        )
        resp.raise_for_status()
