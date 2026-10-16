from dataclasses import dataclass
from types import ModuleType

from . import doi_source, ebsco, pubmed, sciencedirect
from .bib import Entry


@dataclass(frozen=True)
class Provider:
    id: str
    label: str
    tab_title: str  # tab the run must find open (EBSCO's host varies); "" anchors on any tab, access having been verified
    login_url: str  # "" means: the person's own institution page
    module: ModuleType


PROVIDERS = {
    p.id: p
    for p in (
        Provider("sciencedirect", "ScienceDirect", "", "https://www.sciencedirect.com", sciencedirect),
        Provider("pubmed", "PubMed", pubmed.TAB_TITLE, "https://pubmed.ncbi.nlm.nih.gov", pubmed),
        Provider("scopus", "Scopus", "", "https://www.scopus.com", doi_source),
        # WoS only lists the entry; its PDF comes from the publisher via the DOI, so no WoS tab (and no WoS captcha) is needed.
        Provider("wos", "Web of Science (by DOI)", "", "", doi_source),
        Provider("ieee", "IEEE Xplore", "", "https://ieeexplore.ieee.org", doi_source),
        Provider("ebsco", "EBSCO", "EBSCO", ebsco.HOME, ebsco),
        Provider("other", "Other (by DOI)", "", "https://doi.org", doi_source),
    )
}


def sources_for(entry: Entry) -> list[str]:
    """Known databases an entry came from; entries with none go to the generic DOI route."""
    known = [s for s in entry.sources if s in PROVIDERS and s != "other"]
    return known or ["other"]
