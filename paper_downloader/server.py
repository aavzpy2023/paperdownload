import os
import random
import tempfile
import time
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Body, Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from . import auth, browser, egress
from .bib import parse_references
from .providers import PROVIDERS
from .throttle import throttle, url_key
from .workspace import Workspace, manager

COOKIE = "pd_token"
OPEN_STAGGER = (2.0, 4.0)
bearer = HTTPBearer(auto_error=False)

Role = Literal["admin", "user", "guest"]


@asynccontextmanager
async def lifespan(_: FastAPI):
    auth.init_db()
    if port := os.environ.get("PD_PROXY_PORT"):
        egress.start(int(port))
    manager.start_reaper()
    yield
    manager.shutdown()


app = FastAPI(title="Paper Downloader", lifespan=lifespan)


def current_user(request: Request, creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> dict:
    """Bearer header for API calls; the cookie lets nginx authorize the noVNC iframe/WebSocket."""
    token = creds.credentials if creds else request.cookies.get(COOKIE)
    user = auth.user_from_token(token) if token else None
    if user is None:
        raise HTTPException(401, "Not authenticated")
    return user


def workspace(user: Annotated[dict, Depends(current_user)]) -> Workspace:
    return manager.for_user(user)


def running_workspace(ws: Annotated[Workspace, Depends(workspace)]) -> Workspace:
    try:
        manager.ensure_running(ws)
    except RuntimeError as e:
        raise HTTPException(503, str(e)) from None
    return ws


def admin_user(user: Annotated[dict, Depends(current_user)]) -> dict:
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    return user


class Credentials(BaseModel):
    username: str
    password: str


class NewUser(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[\w.@-]+$")
    password: str = Field(min_length=6, max_length=200)
    role: Role = "user"


class UserPatch(BaseModel):
    password: str | None = Field(default=None, min_length=6, max_length=200)
    role: Role | None = None
    active: bool | None = None


class Settings(BaseModel):
    institution_url: str = Field(default="", max_length=500, pattern=r"^(https?://\S+)?$")


class StartBody(BaseModel):
    indices: list[int] | None = None
    site: str = "sciencedirect"
    sites: dict[str, list[int]] | None = None  # site -> row indices, for a selection that mixes databases


class SiteBody(BaseModel):
    site: str | None = None


public = APIRouter(prefix="/api")
private = APIRouter(prefix="/api", dependencies=[Depends(current_user)])
admin = APIRouter(prefix="/api/users", dependencies=[Depends(admin_user)])


@public.post("/auth/login")
def login(body: Credentials, response: Response):
    user = auth.authenticate(body.username, body.password)
    if user is None:
        raise HTTPException(401, "Invalid username or password")
    token = auth.make_token(user)
    response.set_cookie(COOKIE, token, max_age=auth.TOKEN_TTL, httponly=True, samesite="strict")
    return {"token": token, "user": user}


@public.post("/auth/logout")
def logout(request: Request, response: Response):
    """Guests lose their browser profile and downloads here; named users keep theirs."""
    token = request.cookies.get(COOKIE)
    user = auth.user_from_token(token) if token else None
    ws = manager.find(user) if user is not None else None
    if ws is not None:
        manager.release(ws) if user["role"] == "guest" else manager.close_viewer(ws)
    response.delete_cookie(COOKIE)
    return {"ok": True}


@private.patch("/auth/me")
def update_me(body: Settings, user: Annotated[dict, Depends(current_user)]):
    return auth.set_institution_url(user["id"], body.institution_url.strip())


@private.get("/auth/me")
def me(user: Annotated[dict, Depends(current_user)]):
    return {k: v for k, v in user.items() if k != "sid"}


@admin.get("")
def users():
    return auth.list_users()


@admin.post("", status_code=201)
def add_user(body: NewUser):
    try:
        return auth.create_user(body.username, body.password, body.role)
    except ValueError as e:
        raise HTTPException(409, str(e)) from None


@admin.patch("/{user_id}")
def edit_user(user_id: int, body: UserPatch):
    try:
        user = auth.update_user(user_id, password=body.password, role=body.role, active=body.active)
    except ValueError as e:
        raise HTTPException(409, str(e)) from None
    if user is None:
        raise HTTPException(404, "User not found")
    return user


@admin.delete("/{user_id}", status_code=204)
def remove_user(user_id: int, me: Annotated[dict, Depends(admin_user)]):
    if user_id == me["id"]:
        raise HTTPException(409, "You cannot delete your own account")
    try:
        found = auth.delete_user(user_id)
    except ValueError as e:
        raise HTTPException(409, str(e)) from None
    if not found:
        raise HTTPException(404, "User not found")
    manager.forget_user(user_id)


@private.post("/session")
def session(ws: Annotated[Workspace, Depends(workspace)]):
    """Open (or keep alive) the remote view; the page pings this while it is on screen."""
    try:
        manager.open_viewer(ws)
    except RuntimeError as e:
        raise HTTPException(503, str(e)) from None
    return {"ready": True}


@private.delete("/session", status_code=204)
def close_session(ws: Annotated[Workspace, Depends(workspace)]):
    manager.close_viewer(ws)


@private.get("/vnc/auth")
def vnc_auth(user: Annotated[dict, Depends(current_user)]):
    """nginx auth_request target: authorizes /vnc/ and tells nginx which noVNC port is this person's."""
    ws = manager.find(user)
    if ws is None or ws.web_port is None:
        raise HTTPException(403, "The remote view is closed")
    return Response(headers={"X-Vnc-Port": str(ws.web_port)})


@private.post("/upload")
def upload(bib: Annotated[UploadFile, File()], ws: Annotated[Workspace, Depends(workspace)]):
    job = ws.job
    if job.running:
        raise HTTPException(409, "A download is in progress")
    try:
        entries = parse_references(bib.file.read().decode("utf-8", errors="replace"), bib.filename or "")
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    if not entries:
        raise HTTPException(400, "No entries with a title found")
    job.load(entries, bib.filename or "")
    return {"count": len(entries)}


@private.post("/open")
def open_chrome(user: Annotated[dict, Depends(current_user)], ws: Annotated[Workspace, Depends(running_workspace)], body: SiteBody = Body(default_factory=SiteBody)):
    if body.site is not None and body.site not in PROVIDERS:
        raise HTTPException(400, f"Unknown site '{body.site}'")
    institution = user["institution_url"] or browser.START_URL
    url = (PROVIDERS[body.site].login_url if body.site else "") or institution or "https://doi.org"
    if body.site is None and not institution:
        raise HTTPException(400, "Set your institution login URL in Settings first")
    try:
        browser.open_start_page(ws.job.chrome, url)
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {e}") from None
    return {"ok": True}


@private.post("/preflight")
def preflight(ws: Annotated[Workspace, Depends(running_workspace)], body: SiteBody = Body(default_factory=SiteBody)):
    if body.site not in PROVIDERS:
        raise HTTPException(400, f"Unknown site '{body.site}'")
    urls = ws.job.preflight_urls(body.site)
    if not urls:
        raise HTTPException(409, "Nothing pending for this database")
    opened = []
    try:
        for url in urls:
            if opened:
                time.sleep(random.uniform(*OPEN_STAGGER))  # never open several publisher pages at once
            if throttle.acquire(url_key(url), max_wait=30) == "cooldown":
                continue
            ws.job.chrome.launch(url)
            opened.append(url)
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {e}") from None
    if not opened:
        raise HTTPException(409, "These publishers are cooling down after a human check; try again in a few minutes")
    return {"urls": opened}


@private.post("/verify")
def verify(ws: Annotated[Workspace, Depends(running_workspace)], body: SiteBody = Body(default_factory=SiteBody)):
    if body.site not in PROVIDERS:
        raise HTTPException(400, f"Unknown site '{body.site}'")
    if ws.job.running:
        raise HTTPException(409, "A download is in progress")
    if ws.job.verifying:
        raise HTTPException(409, "A verification is already in progress")
    try:
        results = ws.job.verify_access(body.site)
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {e}") from None
    return {"ok": all(r["problem"] is None for r in results), "results": results}


@private.post("/dump")
def dump(ws: Annotated[Workspace, Depends(running_workspace)], body: SiteBody = Body(default_factory=SiteBody)):
    if body.site not in PROVIDERS:
        raise HTTPException(400, f"Unknown site '{body.site}'")
    try:
        path = browser.dump_page(PROVIDERS[body.site].tab_title, ws.job.chrome)
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {e}") from None
    return {"path": str(path)}


@private.post("/start")
def start(ws: Annotated[Workspace, Depends(running_workspace)], body: StartBody = Body(default_factory=StartBody)):
    job = ws.job
    by_site = body.sites or {body.site: body.indices if body.indices is not None else list(range(len(job.rows)))}
    unknown = [s for s in by_site if s not in PROVIDERS]
    if unknown:
        raise HTTPException(400, f"Unknown site '{unknown[0]}'")
    access = job.snapshot()["access"]
    locked = [PROVIDERS[s].label for s in by_site if by_site[s] and access.get(s) == "required"]
    if locked:
        raise HTTPException(409, f"Check access first: {', '.join(locked)}")
    return {"started": job.start({i: s for s, idxs in by_site.items() for i in idxs})}


@private.post("/stop")
def stop(ws: Annotated[Workspace, Depends(workspace)]):
    ws.job.stop()
    return {"ok": True}


@private.get("/zip")
def zip_downloads(ws: Annotated[Workspace, Depends(workspace)]):
    job = ws.job
    pdfs = sorted(job.target.glob("*.pdf")) if job.target.is_dir() else []
    if job.running or not pdfs:
        raise HTTPException(409, "Nothing to zip yet")
    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as z:  # PDFs don't compress further
        for pdf in pdfs:
            z.write(pdf, pdf.name)
    tmp.close()
    return FileResponse(
        tmp.name, media_type="application/zip", filename=f"{job.target.name}.zip",
        background=BackgroundTask(Path(tmp.name).unlink),
    )


@private.get("/providers")
def providers(user: Annotated[dict, Depends(current_user)]):
    return {
        "institution_url": user["institution_url"] or browser.START_URL,
        "providers": [{"id": p.id, "label": p.label, "login_url": p.login_url} for p in PROVIDERS.values()],
    }


@private.get("/state")
def state(ws: Annotated[Workspace, Depends(workspace)]):
    return ws.job.snapshot()


app.include_router(public)
app.include_router(private)
app.include_router(admin)
