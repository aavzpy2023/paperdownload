import re
from pathlib import Path

from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from .bib import Entry

HOME = "https://research.ebsco.com/"
CARD = "article[data-auto='search-result-item']"
TITLE_LINK = "a[data-auto='result-item-title__link']"
TOOLS_BUTTON = "[data-auto='tools-dropdown-indicator']"
DOWNLOAD_ITEM = "[data-auto='menuitem-Download']"


class NotFound(Exception):
    pass


def _slug(text: str, limit: int = 80) -> str:
    return re.sub(r"[^\w.-]+", "_", text).strip("_")[:limit] or "paper"


def _norm(text: str) -> str:
    return re.sub(r"\W+", " ", text.lower()).strip()


def base_url(page: Page) -> str:
    """Institution-scoped base URL (e.g. .../c/abc123) of the tab the user prepared."""
    m = re.match(r"(https://research\.ebsco\.com/c/[^/]+)", page.url)
    return m.group(1) if m else HOME.rstrip("/")


def _search(page: Page, base: str, query: str) -> None:
    page.goto(f"{base}/search", wait_until="domcontentloaded")
    box = page.locator("#search-input")
    box.fill(query)
    box.press("Enter")
    page.wait_for_url(re.compile(r"/search/results"), timeout=30000)
    page.wait_for_selector(f"{CARD}, [data-auto='no-results']", timeout=30000)


def _matching_card(page: Page, title: str):
    cards = page.locator(CARD)
    wanted = _norm(title)
    for i in range(min(cards.count(), 10)):
        card = cards.nth(i)
        found = _norm(card.locator(TITLE_LINK).first.inner_text())
        if found == wanted or wanted in found or found in wanted:
            return card
    return None


def download(page: Page, base: str, entry: Entry, out_dir: Path) -> Path:
    # A DOI search finds the exact record but still returns loosely related
    # ones, so the card is always picked by title.
    _search(page, base, entry.doi or entry.title)
    card = _matching_card(page, entry.title)
    if card is None and entry.doi:
        _search(page, base, entry.title)
        card = _matching_card(page, entry.title)
    if card is None:
        raise NotFound("no result matches the title")

    if (card.locator("h3").first.get_attribute("data-auto") or "").startswith("no_fulltext"):
        raise NotFound("no full text in EBSCO (library link only)")

    card.locator(TOOLS_BUTTON).click()
    item = card.locator(DOWNLOAD_ITEM)
    try:
        item.wait_for(timeout=5000)
    except PlaywrightTimeout:
        raise NotFound("no Download option in the tools menu")

    dest = out_dir / f"{_slug(entry.key or entry.title)}.pdf"
    try:
        with page.expect_download(timeout=60000) as dl:
            item.click()
    except PlaywrightTimeout:
        raise NotFound("Download did not start")
    dl.value.save_as(dest)
    return dest
