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
    journal: str = ""


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


_NBIB_TAG = re.compile(r"^([A-Z]{2,4})\s*-\s?(.*)$")


def parse_nbib(text: str) -> list[Entry]:
    """Parse PubMed's MEDLINE/.nbib export: records split by blank lines, 'TAG - value' lines."""
    entries = []
    for record in re.split(r"\n\s*\n", text.replace("\r\n", "\n").strip()):
        fields: dict[str, list[str]] = {}
        tag = None
        for line in record.splitlines():
            m = _NBIB_TAG.match(line)
            if m:
                tag = m.group(1)
                fields.setdefault(tag, []).append(m.group(2).strip())
            elif tag and line.startswith(" ") and line.strip():
                fields[tag][-1] += " " + line.strip()
        title = _clean(" ".join(fields.get("TI", [])))
        if not title:
            continue
        pmid = (fields.get("PMID") or [""])[0]
        doi = next((v.removesuffix("[doi]").strip() for v in fields.get("LID", []) + fields.get("AID", []) if v.endswith("[doi]")), "")
        year = re.search(r"\d{4}", (fields.get("DP") or [""])[0])
        entries.append(
            Entry(
                key=f"pmid{pmid}" if pmid else re.sub(r"\W+", "", title)[:20],
                title=title,
                authors=" and ".join(fields.get("FAU") or fields.get("AU") or []),
                year=year.group(0) if year else "",
                doi=doi,
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
                sources=("pubmed",),
                journal=(fields.get("JT") or fields.get("TA") or [""])[0],
            )
        )
    return entries


def parse_references(text: str, filename: str) -> list[Entry]:
    """Parse a .bib or .nbib upload; any other format is rejected."""
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if suffix == "bib":
        return parse_bib(text)
    if suffix == "nbib":
        return parse_nbib(text)
    raise ValueError("Only .bib and .nbib files are accepted")


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
                journal=_clean(raw.get("journal", "") or raw.get("booktitle", "")),
            )
        )
    return entries
