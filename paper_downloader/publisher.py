import base64
import re

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from .ebsco import NotFound

PDF_BUTTON = re.compile(r"^\s*(download\s+)?(full[\s-]*text\s+)?pdf\b|download\s+pdf|view\s+pdf", re.I)
FIND_WAIT_S = 20
SUPPLEMENT = re.compile(r"supplement|/esm/|mediaobjects|moesm", re.I)


def fetch_pdf(page: Page, href: str) -> bytes | None:
    """Fetch from inside the page: same origin and session as the browser, no click needed."""
    try:
        encoded = page.evaluate(
            """async (url) => {
                const ctl = new AbortController();
                const timer = setTimeout(() => ctl.abort(), 90000);
                const r = await fetch(url, {signal: ctl.signal});
                const buf = new Uint8Array(await r.arrayBuffer());
                clearTimeout(timer);
                let out = '';
                for (let i = 0; i < buf.length; i += 0x8000)
                    out += String.fromCharCode(...buf.subarray(i, i + 0x8000));
                return btoa(out);
            }""",
            href,
        )
    except PlaywrightError:
        return None
    data = base64.b64decode(encoded)
    return data if data.startswith(b"%PDF") else None


IEEE_ARNUMBER = re.compile(r"ieeexplore\.ieee\.org/(?:abstract/)?(?:document|stamp/stamp\.jsp\?[^#]*arnumber=)/?(\d+)")


def ieee_pdf(page: Page, article_url: str) -> bytes:
    """IEEE Xplore embeds the PDF in an iframe of the stamp page; fetch that source directly."""
    m = IEEE_ARNUMBER.search(article_url)
    if m is None:
        raise NotFound("Could not find the IEEE article number")
    n = m.group(1)
    page.goto(f"https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber={n}", wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    data = fetch_pdf(page, f"https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&arnumber={n}&ref=")
    if data is None:
        raise NotFound("IEEE did not return a PDF (no access, or a human check is pending)")
    return data


HUMAN_CHECK = re.compile(
    r"just a moment|verify you are human|are you a robot|performing security verification|unusual activity", re.I
)
PAYWALL = re.compile(r"get access|purchase (pdf|article)|rent or buy|buy (this )?article|access through your institution", re.I)


def probe_access(page: Page, url: str) -> str | None:
    """Open an article and say what blocks a download (a human check or no access), or None if it looks fine."""
    page.goto(url, wait_until="domcontentloaded", timeout=45000)
    try:
        page.wait_for_url(lambda u: "doi.org" not in u and "linkinghub" not in u, timeout=15000)
    except PlaywrightTimeout:
        pass
    page.wait_for_timeout(6000)
    text = page.title() + " " + page.inner_text("body")[:1500]
    if HUMAN_CHECK.search(text):
        return "human check pending"
    if "ieeexplore.ieee.org" in page.url:
        return None
    if PAYWALL.search(text) and _pdf_control(page).count() == 0:
        return "no institutional access"
    return None


def _pick_control(page: Page):
    """Prefer a literal "Download PDF" over a bare "PDF", which often opens an embedded viewer."""
    every = [c for c in _pdf_control(page).all()
             if not SUPPLEMENT.search(c.inner_text() + (c.get_attribute("href") or ""))]
    controls = [c for c in every if c.is_visible()]
    for c in controls:
        if re.search(r"download\s+pdf", c.inner_text(), re.I):
            return c
    for c in controls:
        if "/epdf" not in (c.get_attribute("href") or ""):
            return c
    for c in every:  # collapsed on narrow screens, but its href can still be fetched
        if (c.get_attribute("href") or "").startswith("http") and re.search(r"download\s+pdf", c.inner_text(), re.I):
            return c
    return controls[0] if controls else None


def _pdf_control(page: Page):
    return page.locator("a, button").filter(has_text=PDF_BUTTON)


def download_pdf(page: Page, url: str, loaded: bool = False) -> bytes:
    """Open a publisher article page and get its PDF through a Download PDF control.

    Publisher sites differ, so this is best effort: it looks for a visible link or
    button labelled "Download PDF" / "PDF" / "View PDF" and tries a same-page fetch of
    its href first, then a real click that triggers a browser download. Pass loaded=True
    when the page is already open on the article.
    """
    if not loaded:
        page.goto(url, wait_until="domcontentloaded")
    try:
        _pdf_control(page).locator("visible=true").first.wait_for(timeout=FIND_WAIT_S * 1000)
    except PlaywrightTimeout:
        if re.search(r"just a moment|verify you are human", page.title() + page.inner_text("body")[:500], re.I):
            raise NotFound("The publisher shows a human check: solve it once in the Remote browser and retry")
        raise NotFound("publisher page has no Download PDF button")
    control = _pick_control(page)
    if control is None:
        raise NotFound("publisher page has no Download PDF button")

    href = control.evaluate("e => e.href || ''")
    if href.startswith(("http://", "https://")):
        data = fetch_pdf(page, href)
        if data is not None:
            return data
    try:
        with page.expect_download(timeout=30000) as dl:
            control.click(timeout=10000)
    except PlaywrightTimeout:
        raise NotFound("publisher Download PDF did not start a download")
    with open(dl.value.path(), "rb") as f:
        data = f.read()
    if not data.startswith(b"%PDF"):
        raise NotFound("publisher download was not a PDF")
    return data
