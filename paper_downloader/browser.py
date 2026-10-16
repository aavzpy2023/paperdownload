import os
import platform
import shutil
import signal
import subprocess
import time
import urllib.request
from urllib.parse import quote
import threading
from dataclasses import dataclass, field
from pathlib import Path

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

SYSTEM = platform.system()
START_TIMEOUT_S = 60
START_URL = os.environ.get("PD_START_URL", "")  # default institution page; each user can set their own
DEBUG_DIR = Path(__file__).resolve().parent.parent / "debug"


def _chrome_bin() -> str:
    if SYSTEM == "Darwin":
        candidates = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    elif SYSTEM == "Windows":
        roots = [os.environ.get(v, "") for v in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]
        candidates = [f"{r}/Google/Chrome/Application/chrome.exe" for r in roots if r]
    else:
        candidates = [shutil.which(n) or "" for n in ("google-chrome-stable", "google-chrome", "chromium")]
    for path in candidates:
        if path and Path(path).exists():
            return path
    raise RuntimeError("Chrome not found; install Google Chrome")


@dataclass
class Chrome:
    """One Chrome instance: its own profile dir, CDP port and X display."""

    work_dir: Path
    port: int
    display: str | None = None
    proc: subprocess.Popen | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def debugger_up(self) -> bool:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json/version", timeout=1)
            return True
        except OSError:
            return False

    def launch(self, url: str | None = None) -> None:
        """Make sure Chrome is up and, if given, open `url` in it. Calls are serialized."""
        with self._lock:
            if not self.debugger_up():
                self._spawn(url)
                return
            if url:
                req = urllib.request.Request(
                    f"http://127.0.0.1:{self.port}/json/new?{quote(url, safe=':/?&=%')}", method="PUT"
                )
                urllib.request.urlopen(req, timeout=5)

    @staticmethod
    def _egress_flags() -> list[str]:
        """Send all traffic, loopback included, through the filtering proxy (see egress.py)."""
        port = os.environ.get("PD_PROXY_PORT")
        if not port:
            return []
        return [f"--proxy-server=http://127.0.0.1:{port}", "--proxy-bypass-list=<-loopback>", "--disable-quic"]

    def _spawn(self, url: str | None) -> None:
        self.work_dir.mkdir(parents=True, exist_ok=True)
        # No Chrome of ours is running here, so these locks are leftovers of a killed one and
        # would make the new Chrome think the profile is in use and exit.
        for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
            (self.work_dir / name).unlink(missing_ok=True)
        env = {**os.environ, **({"DISPLAY": self.display} if self.display else {})}
        self.proc = subprocess.Popen(
            [
                _chrome_bin(),
                f"--remote-debugging-port={self.port}",
                f"--user-data-dir={self.work_dir}",
                "--profile-directory=Default",
                "--no-first-run",
                "--no-default-browser-check",
                "--start-maximized",
                *(["--no-sandbox"] if os.environ.get("PD_CHROME_NO_SANDBOX") else []),
                *self._egress_flags(),
                *([url] if url else []),
            ],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        # A busy machine can take a minute to bring Chrome up.
        for _ in range(START_TIMEOUT_S * 2):
            if self.debugger_up():
                return
            if self.proc.poll() is not None:
                raise RuntimeError(f"Chrome exited while starting (code {self.proc.returncode})")
            time.sleep(0.5)
        raise RuntimeError("Chrome did not expose the debugging port in time. Try again in a moment.")

    def close(self) -> None:
        if self.proc is None:
            return
        try:
            os.killpg(self.proc.pid, signal.SIGTERM)
            self.proc.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            pass
        self.proc = None


def connect(pw: Playwright, chrome: Chrome) -> Browser:
    chrome.launch()
    return pw.chromium.connect_over_cdp(f"http://127.0.0.1:{chrome.port}")


def open_start_page(chrome: Chrome, url: str) -> None:
    chrome.launch(url)


def find_tab(browser: Browser, title_part: str = "EBSCO") -> Page:
    for context in browser.contexts:
        for page in context.pages:
            if title_part.lower() in page.title().lower():
                return page
    raise RuntimeError(f"No browser tab with '{title_part}' in its title. Open and sign in to that site first.")


def dump_page(title_part: str, chrome: Chrome) -> Path:
    """Save the HTML of the matching tab so selectors can be written against it."""
    with sync_playwright() as pw:
        br = connect(pw, chrome)
        page = find_tab(br, title_part)
        DEBUG_DIR.mkdir(exist_ok=True)
        out = DEBUG_DIR / time.strftime(f"{title_part.lower()}_%H%M%S.html")
        out.write_text(f"<!-- {page.url} -->\n" + page.content(), encoding="utf-8")
        return out


def new_background_page(context: BrowserContext, anchor: Page) -> Page:
    """Open a tab without activating it, so Chrome doesn't steal keyboard/mouse focus."""
    cdp = context.new_cdp_session(anchor)
    try:
        with context.expect_page() as info:
            cdp.send("Target.createTarget", {"url": "about:blank", "background": True})
        return info.value
    finally:
        cdp.detach()
