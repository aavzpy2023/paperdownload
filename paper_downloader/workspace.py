import os
import shutil
import socket
import signal
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import auth, browser
from .job import Job

ROOT = Path(__file__).resolve().parent.parent
MAX_SESSIONS = int(os.environ.get("PD_MAX_SESSIONS", 6))
IDLE_SECONDS = {"guest": 30 * 60, "persistent": 120 * 60}
VIEWER_IDLE_SECONDS = 5 * 60  # the remote view closes itself when the page stops pinging
SCREEN = "1366x768x24"
X_SOCKETS = Path("/tmp/.X11-unix")
NOVNC_DIR = "/usr/share/novnc"


@dataclass
class Workspace:
    """A person's download job plus, while active, a private desktop with its own Chrome."""

    key: str
    guest: bool
    profile_dir: Path
    job: Job
    slot: int | None = None
    procs: list[subprocess.Popen] = field(default_factory=list)
    viewer_procs: list[subprocess.Popen] = field(default_factory=list)
    viewer_on: bool = False
    viewer_seen: float = 0.0
    last_seen: float = field(default_factory=time.time)

    @property
    def web_port(self) -> int | None:
        """noVNC port, only while the remote view is deliberately open."""
        return 6100 + self.slot if self.viewer_on and self.slot is not None else None


def _wait_port(port: int, timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def _spawn(args: list[str], env: dict | None = None) -> subprocess.Popen:
    return subprocess.Popen(
        args, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True
    )


def _kill(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass


class Manager:
    """Registry of workspaces.

    Signed-in 'user'/'admin' accounts get one workspace per account with a
    persistent Chrome profile (saved logins). 'guest' accounts get one per
    login session with a throw-away profile and download folder.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._spaces: dict[str, Workspace] = {}
        self._reaper: threading.Thread | None = None
        self._stopping = threading.Event()

    def for_user(self, user: dict) -> Workspace:
        guest = user["role"] == "guest"
        key = f"guest:{user['sid']}" if guest else f"user:{user['id']}"
        with self._lock:
            ws = self._spaces.get(key)
            if ws is None:
                if guest:
                    profile_dir = Path(tempfile.gettempdir()) / f"pd-guest-{user['sid']}"
                    out_dir = ROOT / "downloads" / f"guest-{user['sid'][:8]}"
                else:
                    profile_dir = auth.DATA_DIR / "profiles" / str(user["id"])
                    out_dir = ROOT / "downloads" / f"{user['id']}-{user['username']}"
                ws = self._spaces[key] = Workspace(key, guest, profile_dir, Job(out_dir=out_dir))
            ws.last_seen = time.time()
            return ws

    def find(self, user: dict) -> Workspace | None:
        key = f"guest:{user['sid']}" if user["role"] == "guest" else f"user:{user['id']}"
        with self._lock:
            ws = self._spaces.get(key)
            if ws is not None:
                ws.last_seen = time.time()
            return ws

    def ensure_running(self, ws: Workspace) -> None:
        """Start the private desktop (Xvfb, VNC, noVNC) and give the job its Chrome. Raises RuntimeError."""
        with self._lock:
            if ws.slot is not None:
                return
            used = {w.slot for w in self._spaces.values() if w.slot is not None}
            free = next((n for n in range(MAX_SESSIONS) if n not in used), None)
            if free is None:
                raise RuntimeError("Too many active browser sessions; try again later")
            ws.slot = free
            try:
                self._start_desktop(ws)
            except Exception:
                self._stop_desktop(ws)
                raise

    def _start_desktop(self, ws: Workspace) -> None:
        n = ws.slot
        display = 100 + n
        for stale in (X_SOCKETS / f"X{display}", Path(f"/tmp/.X{display}-lock")):
            stale.unlink(missing_ok=True)
        ws.procs = [_spawn(["Xvfb", f":{display}", "-screen", "0", SCREEN, "-nolisten", "tcp"])]
        for _ in range(50):
            if (X_SOCKETS / f"X{display}").exists():
                break
            time.sleep(0.1)
        else:
            raise RuntimeError("Virtual display did not start")
        ws.procs.append(_spawn(["fluxbox"], {**os.environ, "DISPLAY": f":{display}"}))
        ws.job.chrome = browser.Chrome(ws.profile_dir, 9300 + n, f":{display}")

    def open_viewer(self, ws: Workspace) -> None:
        """Expose the private desktop through noVNC. Raises RuntimeError."""
        with self._lock:
            self.ensure_running(ws)
            ws.viewer_seen = time.time()
            if ws.viewer_on:
                return
            try:
                self._start_viewer(ws)
            except Exception:
                self._stop_viewer(ws)
                raise
            ws.viewer_on = True

    def _start_viewer(self, ws: Workspace) -> None:
        display, vnc, web = 100 + ws.slot, 5910 + ws.slot, 6100 + ws.slot
        ws.viewer_procs = [
            _spawn(["x11vnc", "-display", f":{display}", "-forever", "-shared", "-rfbport", str(vnc),
                    "-localhost", "-nopw", "-q"]),
            _spawn(["websockify", "--web", NOVNC_DIR, f"0.0.0.0:{web}", f"127.0.0.1:{vnc}"]),  # reachable from nginx on the private network only
        ]
        # The page connects as soon as the view is reported open, so wait for both listeners.
        if not (_wait_port(vnc) and _wait_port(web)):
            raise RuntimeError("The remote view did not start")

    def _stop_viewer(self, ws: Workspace) -> None:
        for proc in reversed(ws.viewer_procs):
            _kill(proc)
        ws.viewer_procs, ws.viewer_on = [], False

    def close_viewer(self, ws: Workspace) -> None:
        with self._lock:
            self._stop_viewer(ws)

    def _stop_desktop(self, ws: Workspace) -> None:
        self._stop_viewer(ws)
        if ws.job.chrome is not None:
            ws.job.chrome.close()
        for proc in reversed(ws.procs):
            _kill(proc)
        ws.procs, ws.slot, ws.job.chrome = [], None, None

    def release(self, ws: Workspace) -> None:
        """Tear the workspace down; guests also lose their profile and downloads."""
        with self._lock:
            ws.job.stop()
            self._stop_desktop(ws)
            if ws.guest:
                self._spaces.pop(ws.key, None)
                shutil.rmtree(ws.profile_dir, ignore_errors=True)
                shutil.rmtree(ws.job.out_dir, ignore_errors=True)

    def forget_user(self, user_id: int) -> None:
        with self._lock:
            ws = self._spaces.pop(f"user:{user_id}", None)
            if ws is not None:
                ws.job.stop()
                self._stop_desktop(ws)
            shutil.rmtree(auth.DATA_DIR / "profiles" / str(user_id), ignore_errors=True)

    def reap_idle(self) -> None:
        now = time.time()
        with self._lock:
            for ws in list(self._spaces.values()):
                if ws.viewer_on and now - ws.viewer_seen > VIEWER_IDLE_SECONDS:
                    self._stop_viewer(ws)
                limit = IDLE_SECONDS["guest" if ws.guest else "persistent"]
                if now - ws.last_seen < limit or ws.job.running:
                    continue
                if ws.guest:
                    self.release(ws)
                elif ws.slot is not None:
                    self._stop_desktop(ws)

    def start_reaper(self) -> None:
        def loop() -> None:
            while not self._stopping.wait(60):
                self.reap_idle()

        self._reaper = threading.Thread(target=loop, daemon=True)
        self._reaper.start()

    def shutdown(self) -> None:
        self._stopping.set()
        with self._lock:
            for ws in list(self._spaces.values()):
                ws.job.stop()
                self._stop_desktop(ws)


manager = Manager()
