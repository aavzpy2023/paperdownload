import re
from pathlib import Path

from playwright.sync_api import Page

from .bib import Entry, clean_doi
from .ebsco import NotFound, _slug
from .publisher import IEEE_ARNUMBER, HumanCheck, ieee_pdf
from .pubmed import from_publisher

# Scopus, Web of Science and IEEE are indexes or portals without a stable search flow here:
# the article is reached through its DOI (or the index record's publisher link) and the
# publisher page, using the institutional session of the browser the person prepared.

INDEX_HOSTS = ("scopus.com", "webofscience.com")
PUBLISHER_LINK = re.compile(r"(view|full\s*text)\s*(at|from)\s*(the\s*)?publisher|full\s*text\s*at\s*publisher", re.I)
FULL_TEXT_MENU = re.compile(r"^\s*full\s*text", re.I)
HUMAN_CHECK = "verify you are human"


def base_url(page: Page) -> str:
    return page.url


def _publisher_href(page: Page, record_url: str) -> str:
    """Read the 'View at Publisher' link from a Scopus / Web of Science record page."""
    page.goto(record_url, wait_until="domcontentloaded")
    page.wait_for_timeout(8000)
    if HUMAN_CHECK in page.inner_text("body").lower():
        raise HumanCheck("The database asks to verify you are human: solve it in the remote browser and retry")
    link = page.locator("a[href]").filter(has_text=PUBLISHER_LINK).first
    if link.count() == 0:
        menu = page.locator("button, a").filter(has_text=FULL_TEXT_MENU).first
        if menu.count() > 0:
            menu.click(timeout=5000)
            page.wait_for_timeout(1500)
            link = page.locator("a[href]").filter(has_text=PUBLISHER_LINK).first
    if link.count() == 0:
        raise NotFound("The record has no publisher link")
    return link.get_attribute("href") or ""


def download(page: Page, base: str, entry: Entry, out_dir: Path) -> Path:
    doi = clean_doi(entry.doi)
    if IEEE_ARNUMBER.search(entry.url):
        result = ieee_pdf(page, entry.url)
    elif any(h in entry.url for h in INDEX_HOSTS):
        result = from_publisher(page, _publisher_href(page, entry.url), entry, out_dir)
    elif doi:
        result = from_publisher(page, f"https://doi.org/{doi}", entry, out_dir)
    else:
        raise NotFound("Entry has no DOI")
    if isinstance(result, Path):
        return result
    dest = out_dir / f"{_slug(entry.key or entry.title)}.pdf"
    dest.write_bytes(result)
    return dest
