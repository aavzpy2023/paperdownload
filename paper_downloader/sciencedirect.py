import base64
import re
from pathlib import Path
from urllib.parse import quote, urljoin

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from .bib import Entry
from . import publisher as publisher_site
from .ebsco import NotFound, _norm, _slug

TAB_TITLE = "ScienceDirect"
BASE = "https://www.sciencedirect.com"
RESULT_LINK = "a.result-list-title-link"
VIEWER_URL = re.compile(r"pdf\.sciencedirectassets\.com")
PUBLISHER_LINK = re.compile(r"(view|go)\s+(at|to|on)\s+(the\s+)?publisher", re.I)
VIEW_PDF = re.compile(r"view\s*pdf|download\s*pdf", re.I)


def base_url(page: Page) -> str:
    return BASE


POPUP_CLOSE = (
    "[role=dialog] button[aria-label*=close i], [role=dialog] button[aria-label*=dismiss i], "
    "[role=dialog] button:has-text('No thanks'), [role=dialog] button:has-text('Maybe later'), "
    "[role=dialog] button:has-text('Not now'), [role=alertdialog] button, "
    "button[aria-label*='close' i]:visible, button:has-text('×'):visible"
)


def _dismiss_popups(page: Page) -> None:
    """Close promo/suggestion overlays that cover the View PDF link."""
    for _ in range(3):
        closers = page.locator(POPUP_CLOSE)
        try:
            if closers.count() == 0:
                break
            closers.first.click(timeout=2000)
        except PlaywrightTimeout:
            page.keyboard.press("Escape")
        page.wait_for_timeout(300)


BLOCK_TEXT = "There was a problem providing the content you requested"


class Blocked(Exception):
    """ScienceDirect/Cloudflare is refusing requests; continuing only prolongs the block."""


def _check_blocked(page: Page) -> None:
    try:
        text = page.locator("body").inner_text(timeout=2000)
    except PlaywrightError:
        return
    if BLOCK_TEXT in text:
        raise Blocked("ScienceDirect blocked this session (Cloudflare). Wait a while and retry")


TURNSTILE = "iframe[src*='challenges.cloudflare.com']"


def _click_turnstile(page: Page) -> bool:
    """Click the Cloudflare checkbox. It lives in a cross-origin iframe with a closed
    shadow root, so click by position: the box sits at the left edge of the widget."""
    frame = page.locator(TURNSTILE).first
    try:
        box = frame.bounding_box(timeout=1000)
    except PlaywrightTimeout:
        return False
    if not box or box["width"] < 50:
        return False
    page.mouse.click(box["x"] + 28, box["y"] + box["height"] / 2)
    return True


def _wait_through_challenge(page: Page, done, max_s: int) -> None:
    """Poll until done() is true, clicking the Cloudflare checkbox whenever it shows up."""
    waited = 0
    while not done():
        if waited >= max_s:
            raise PlaywrightTimeout("challenge not solved")
        if waited % 5 == 2:
            _check_blocked(page)
            _click_turnstile(page)
        page.wait_for_timeout(1000)
        waited += 1


def _viewer_pdf(page: Page, href: str) -> bytes:
    """Open the View PDF link in this same (background) tab and read the file from it.

    Requests made outside the browser hit a Cloudflare check, but a same-origin
    fetch from the viewer page that already passed it returns the PDF.
    """
    try:
        page.goto(href, wait_until="commit")
        _wait_through_challenge(page, lambda: bool(VIEWER_URL.search(page.url)), 90)
        encoded = page.evaluate(
            """async () => {
                const ctl = new AbortController();
                const timer = setTimeout(() => ctl.abort(), 90000);
                const buf = new Uint8Array(await (await fetch(location.href, {signal: ctl.signal})).arrayBuffer());
                clearTimeout(timer);
                let out = '';
                for (let i = 0; i < buf.length; i += 0x8000)
                    out += String.fromCharCode(...buf.subarray(i, i + 0x8000));
                return btoa(out);
            }"""
        )
    except PlaywrightTimeout:
        _check_blocked(page)
        raise NotFound("viewer did not reach the PDF (captcha?)")
    except PlaywrightError as e:
        if "AbortError" in str(e):
            raise NotFound("PDF read timed out after 90 s")
        raise
    data = base64.b64decode(encoded)
    if not data.startswith(b"%PDF"):
        raise NotFound("View PDF did not return a PDF")
    return data


def _search(page: Page, query: str) -> None:
    page.goto(f"{BASE}/search?qs={quote(query)}", wait_until="domcontentloaded")
    try:
        page.wait_for_selector(f"{RESULT_LINK}, .search-body-results-text", timeout=30000)
    except PlaywrightTimeout:
        raise NotFound("search page did not load (captcha or layout change?)")


def _matching_href(page: Page, title: str) -> str | None:
    links = page.locator(RESULT_LINK)
    wanted = _norm(title)
    for i in range(min(links.count(), 10)):
        found = _norm(links.nth(i).inner_text())
        if found == wanted or wanted in found or found in wanted:
            return urljoin(page.url, links.nth(i).get_attribute("href") or "")
    return None


def has_url(entry: Entry) -> bool:
    return "sciencedirect.com" in entry.url


def download(page: Page, base: str, entry: Entry, out_dir: Path) -> Path:
    if has_url(entry):
        href = entry.url
    else:
        _search(page, entry.doi or entry.title)
        href = _matching_href(page, entry.title)
        if href is None and entry.doi:
            _search(page, entry.title)
            href = _matching_href(page, entry.title)
        if href is None:
            raise NotFound("no result matches the title")

    page.goto(href, wait_until="domcontentloaded")
    pii = re.search(r"/pii/(\w+)", page.url)
    links = page.get_by_role("link", name=VIEW_PDF)
    if pii:
        # Recommended articles on the page carry their own "View PDF" links.
        links = links.and_(page.locator(f"a[href*='{pii.group(1)}']"))
    link = links.first
    publisher = page.get_by_role("link", name=PUBLISHER_LINK)
    _dismiss_popups(page)
    try:
        _wait_through_challenge(page, lambda: link.count() > 0 or publisher.count() > 0, 25)
    except PlaywrightTimeout:
        _check_blocked(page)
        raise NotFound("no View PDF link (no access, or Cloudflare not solved)")

    if link.count() == 0:
        # View PDF may still be loading next to the publisher link; give it a moment.
        page.wait_for_timeout(3000)
    if link.count() == 0:
        data = publisher_site.download_pdf(page, publisher.first.evaluate("e => e.href"))
        dest = out_dir / f"{_slug(entry.key or entry.title)}.pdf"
        dest.write_bytes(data)
        return dest

    data = _viewer_pdf(page, urljoin(page.url, link.get_attribute("href") or ""))

    dest = out_dir / f"{_slug(entry.key or entry.title)}.pdf"
    dest.write_bytes(data)
    return dest
