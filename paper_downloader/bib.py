import re
from dataclasses import dataclass

import bibtexparser
from bibtexparser.bparser import BibTexParser


@dataclass(frozen=True)
class Entry:
    key: str
    title: str
    authors: str
    year: str
    doi: str
    url: str = ""
    sources: tuple[str, ...] = ()


def clean_doi(doi: str) -> str:
    return doi.removeprefix("https://doi.org/").removeprefix("http://dx.doi.org/").strip()


def _clean(value: str) -> str:
    return " ".join(value.replace("{", "").replace("}", "").split())


# Screening exports annotate each entry with "% ... (sources: wos;scopus)" just above it.
_SOURCES = re.compile(r"^%[^\n]*\(sources:\s*([^)]*)\)[^\n]*\n(?:[ \t]*\n)*@\w+\s*\{\s*([^,\s]+)\s*,", re.M)
_ALIASES = {"web of science": "wos", "webofscience": "wos", "ieeexplore": "ieee", "ieee xplore": "ieee"}


def _annotated_sources(text: str) -> dict[str, tuple[str, ...]]:
    found = {}
    for m in _SOURCES.finditer(text):
        names = (_ALIASES.get(n.strip().lower(), n.strip().lower()) for n in re.split(r"[;,]", m.group(1)))
        found[m.group(2)] = tuple(dict.fromkeys(n for n in names if n))
    return found


def _infer_sources(url: str, doi: str) -> tuple[str, ...]:
    hosts = {"sciencedirect.com": "sciencedirect", "pubmed.ncbi.nlm.nih.gov": "pubmed", "ieeexplore.ieee.org": "ieee"}
    found = [name for host, name in hosts.items() if host in url]
    if doi.startswith("10.1109/") and "ieee" not in found:
        found.append("ieee")
    return tuple(found)


def parse_bib(text: str) -> list[Entry]:
    parser = BibTexParser(common_strings=True, ignore_nonstandard_types=False)
    db = bibtexparser.loads(text, parser=parser)
    annotated = _annotated_sources(text)
    entries = []
    for raw in db.entries:
        title = _clean(raw.get("title", ""))
        if not title:
            continue
        key, doi, url = raw.get("ID", ""), _clean(raw.get("doi", "")), _clean(raw.get("url", ""))
        sources = tuple(dict.fromkeys(annotated.get(key, ()) + _infer_sources(url, doi)))
        entries.append(
            Entry(
                key=key,
                title=title,
                authors=_clean(raw.get("author", "")),
                year=_clean(raw.get("year", "")),
                doi=doi,
                url=url,
                sources=sources,
            )
        )
    return entries
