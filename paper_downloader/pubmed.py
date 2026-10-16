from dataclasses import replace
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from .bib import Entry
from .ebsco import NotFound, _slug
from . import publisher, sciencedirect
from .publisher import fetch_pdf

# PubMed needs no login, so any open tab can serve as the anchor for background tabs.
TAB_TITLE = ""
FULL_TEXT_LINK = ".full-text-links-list a[data-ga-action='{}']"
MDPI_PDF = "a.UD_ArticlePDF"
PMC_PDF_HREF = """() => {
    const a = [...document.querySelectorAll('a[href$=".pdf"]')]
        .find(a => a.href.startsWith(location.origin + '/articles/PMC'));
    return a ? a.href : null;
}"""
RETRY_WAIT_MS = 8000


def has_url(entry: Entry) -> bool:
    return "pubmed.ncbi.nlm.nih.gov" in entry.url


def base_url(page: Page) -> str:
    return "https://pubmed.ncbi.nlm.nih.gov"


def _from_mdpi(page: Page, href: str) -> bytes:
    page.goto(href, wait_until="domcontentloaded")
    link = page.locator(MDPI_PDF).first
    try:
        link.wait_for(state="attached", timeout=20000)
    except PlaywrightTimeout:
        raise NotFound("MDPI page has no Download PDF link")
    data = fetch_pdf(page, link.evaluate("e => e.href"))
    if data is None:
        raise NotFound("MDPI did not return a PDF")
    return data


def _from_pmc(page: Page, href: str) -> bytes:
    page.goto(href, wait_until="domcontentloaded")
    pdf_href = None
    for attempt in range(2):
        try:
            page.wait_for_function(PMC_PDF_HREF, timeout=20000)
            pdf_href = page.evaluate(PMC_PDF_HREF)
        except PlaywrightTimeout:
            pdf_href = None
        if pdf_href:
            # Fetching the PDF cold returns PMC's anti-bot interstitial; requesting it once
            # through the browser makes it set the cookie that lets the fetch below succeed.
            try:
                page.goto(pdf_href, wait_until="commit", timeout=15000)
            except PlaywrightError:
                pass
            page.wait_for_timeout(2000)
        data = fetch_pdf(page, pdf_href) if pdf_href else None
        if data is not None:
            return data
        if attempt == 0:
            # PMC often rejects the first request; a pause and a retry usually works.
            page.wait_for_timeout(RETRY_WAIT_MS)
    if pdf_href is None:
        raise NotFound("PMC article has no PDF (embargoed or HTML only)")
    raise NotFound("PMC did not return a PDF")


def from_publisher(page: Page, href: str, entry: Entry, out_dir: Path) -> Path | bytes:
    """Follow a generic PubMed full-text link: ScienceDirect has its own flow, others use the
    Download PDF button on the publisher page."""
    page.goto(href, wait_until="domcontentloaded")
    try:
        # linkinghub.elsevier.com and doi.org redirect to the real article page.
        page.wait_for_url(lambda url: "linkinghub" not in url and "doi.org" not in url, timeout=20000)
    except PlaywrightTimeout:
        pass
    if "sciencedirect.com" in page.url:
        return sciencedirect.download(page, sciencedirect.BASE, replace(entry, url=page.url), out_dir)
    if "ieeexplore.ieee.org" in page.url:
        return publisher.ieee_pdf(page, page.url)
    return publisher.download_pdf(page, page.url, loaded=True)


def download(page: Page, base: str, entry: Entry, out_dir: Path) -> Path:
    page.goto(entry.url, wait_until="domcontentloaded")
    try:
        page.locator(".full-text-links-list a").first.wait_for(timeout=10000)
    except PlaywrightTimeout:
        raise NotFound("PubMed has no full-text link")
    attempts = []
    for name, handler in (("MDPI", _from_mdpi), ("PMC", _from_pmc)):
        link = page.locator(FULL_TEXT_LINK.format(name)).first
        if link.count() > 0:
            attempts.append((handler, link.get_attribute("href") or ""))
    others = page.locator(".full-text-links-list a:not([data-ga-action='MDPI']):not([data-ga-action='PMC'])")
    if others.count() > 0:
        attempts.append((None, others.first.get_attribute("href") or ""))
    if not attempts:
        raise NotFound("PubMed has no full-text link")

    error = None
    for handler, href in attempts:
        try:
            if handler is None:
                result = from_publisher(page, href, entry, out_dir)
            else:
                result = handler(page, href)
        except NotFound as e:
            error = e
            page.goto(entry.url, wait_until="domcontentloaded")
            continue
        if isinstance(result, Path):
            return result
        dest = out_dir / f"{_slug(entry.key or entry.title)}.pdf"
        dest.write_bytes(result)
        return dest
    raise error
