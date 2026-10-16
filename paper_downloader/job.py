import random
import threading
from datetime import date
from dataclasses import dataclass, field
from pathlib import Path

from playwright.sync_api import sync_playwright

from . import browser, ebsco, publisher, sciencedirect
from urllib.parse import urlparse

from .bib import Entry, clean_doi
from .ebsco import _slug
from .providers import PROVIDERS, sources_for

PAUSE_RANGE = (10.0, 20.0)
PENDING, RUNNING, DONE, FAILED = "pending", "running", "done", "failed"


@dataclass
class Row:
    entry: Entry
    status: str = PENDING
    detail: str = ""


@dataclass
class Job:
    out_dir: Path
    rows: list[Row] = field(default_factory=list)
    running: bool = False
    error: str = ""
    chrome: browser.Chrome | None = None
    site: str = "sciencedirect"
    selected: set[int] | None = None
    folder: Path | None = None
    access_ok: set[str] = field(default_factory=set)
    _stop: threading.Event = field(default_factory=threading.Event)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def target(self) -> Path:
        return self.folder or self.out_dir

    def load(self, entries: list[Entry], bib_name: str = "") -> None:
        """Download into downloads/<bib name>_<YYYYMMDD>/ and mark PDFs already there as done."""
        with self._lock:
            stem = _slug(Path(bib_name).stem) if bib_name else ""
            self.folder = self.out_dir / f"{stem}_{date.today():%Y%m%d}" if stem else None
            self.rows = [Row(e) for e in entries]
            for r in self.rows:
                pdf = self.target / f"{_slug(r.entry.key or r.entry.title)}.pdf"
                if pdf.is_file():
                    r.status, r.detail = DONE, f"{pdf.name} (already in folder)"
            self.error = ""
            self.access_ok.clear()

    def _sync_with_folder(self) -> None:
        """Count PDFs dropped into the folder by hand (named <key>.pdf) as done."""
        for r in self.rows:
            if r.status in (DONE, RUNNING):
                continue
            pdf = self.target / f"{_slug(r.entry.key or r.entry.title)}.pdf"
            if pdf.is_file():
                r.status, r.detail = DONE, f"{pdf.name} (already in folder)"

    def preflight_urls(self, site: str, limit: int = 10) -> list[str]:
        """One article per publisher (DOI prefix, else URL host) still to download from `site`.

        Opening them in the visible browser up front lets the person solve each publisher's
        captcha or login once, before the unattended run.
        """
        found: dict[str, str] = {}
        with self._lock:
            for r in self.rows:
                e = r.entry
                if r.status == DONE or site not in sources_for(e):
                    continue
                doi = clean_doi(e.doi)
                key = doi.split("/")[0] if doi else urlparse(e.url).netloc
                url = f"https://doi.org/{doi}" if doi else e.url
                if key and url and key not in found:
                    found[key] = url
        return list(found.values())[:limit]

    def verify_access(self, site: str) -> list[dict]:
        """Probe the sampled articles of `site` in background tabs; the site is unlocked only if all pass."""
        urls = self.preflight_urls(site)
        results = []
        if urls and self.chrome is None:
            raise RuntimeError("Browser session is not running")
        if urls:
            with sync_playwright() as pw:
                br = browser.connect(pw, self.chrome)
                context = br.contexts[0]
                for url in urls:
                    page = context.new_page()
                    page.bring_to_front()  # visible in the Remote browser while it is checked
                    try:
                        problem = publisher.probe_access(page, url)
                    except Exception as e:
                        problem = f"{type(e).__name__}: {e}"[:120]
                    finally:
                        page.close()
                    results.append({"url": url, "problem": problem})
        if all(r["problem"] is None for r in results):
            self.access_ok.add(site)
        else:
            self.access_ok.discard(site)
        return results

    def snapshot(self) -> dict:
        with self._lock:
            self._sync_with_folder()
            rows = [
                {
                    "key": r.entry.key, "title": r.entry.title, "authors": r.entry.authors,
                    "year": r.entry.year, "sources": sources_for(r.entry), "status": r.status, "detail": r.detail,
                }
                for r in self.rows
            ]
            counts = {s: sum(r.status == s for r in self.rows) for s in (PENDING, RUNNING, DONE, FAILED)}
        can_zip = not self.running and any(r.status == DONE for r in self.rows)
        sites = {s for r in self.rows for s in sources_for(r.entry)}
        # "none": nothing pending to check for that database, so no access is needed.
        access = {
            s: "ok" if s in self.access_ok else ("required" if self.preflight_urls(s) else "none")
            for s in sites
        }
        pdf_count = len(list(self.target.glob("*.pdf"))) if self.target.is_dir() else 0
        return {"access": access, "pdf_count": pdf_count, "running": self.running, "can_zip": can_zip, "error": self.error, "rows": rows, "counts": counts,
                "out_dir": str(self.target)}

    def start(self, indices: list[int] | None = None) -> bool:
        with self._lock:
            if self.running or not self.rows:
                return False
            self.selected = None if indices is None else set(indices)
            if self.selected is not None and not self.selected:
                return False
            self.running = True
            self.error = ""
            self._stop.clear()
        threading.Thread(target=self._run, daemon=True).start()
        return True

    def stop(self) -> None:
        self._stop.set()

    def _set(self, row: Row, status: str, detail: str = "") -> None:
        with self._lock:
            row.status, row.detail = status, detail

    def _run(self) -> None:
        self.target.mkdir(parents=True, exist_ok=True)
        try:
            with sync_playwright() as pw:
                if self.chrome is None:
                    raise RuntimeError("Browser session is not running")
                br = browser.connect(pw, self.chrome)
                title_part, provider = PROVIDERS[self.site].tab_title, PROVIDERS[self.site].module
                tab = browser.find_tab(br, title_part)
                base = provider.base_url(tab)
                started = False
                for i, row in enumerate(self.rows):
                    if self._stop.is_set():
                        break
                    if row.status == DONE:
                        continue
                    if self.selected is not None and i not in self.selected:
                        continue
                    if started and self._stop.wait(random.uniform(*PAUSE_RANGE)):
                        break
                    started = True
                    self._set(row, RUNNING)
                    # A fresh tab per paper: one crashed renderer must not poison the rest.
                    page = browser.new_background_page(tab.context, tab)
                    try:
                        path = provider.download(page, base, row.entry, self.target)
                        self._set(row, DONE, path.name)
                    except sciencedirect.Blocked as e:
                        self._set(row, PENDING)
                        self.access_ok.discard(self.site)
                        self.error = str(e)
                        self._stop.set()
                    except ebsco.NotFound as e:
                        self._set(row, FAILED, str(e))
                    except Exception as e:  # keep going on per-article errors
                        self._set(row, FAILED, f"{type(e).__name__}: {e}"[:200])
                    finally:
                        try:
                            page.close()
                        except Exception:
                            pass
        except Exception as e:
            self.error = f"{type(e).__name__}: {e}"
        finally:
            with self._lock:
                for r in self.rows:
                    if r.status == RUNNING:
                        r.status = PENDING
                self.running = False
