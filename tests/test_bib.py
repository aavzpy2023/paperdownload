from paper_downloader.bib import parse_bib

SAMPLE = """
@article{smith2020,
  title = {A {Nice} Study
           of Things},
  author = {Smith, John and Doe, Jane},
  year = {2020},
  doi = {10.1000/xyz}
}
@misc{notitle, author = {X}}
"""


def test_parse_cleans_braces_and_skips_untitled():
    entries = parse_bib(SAMPLE)
    assert len(entries) == 1
    e = entries[0]
    assert e.key == "smith2020"
    assert e.title == "A Nice Study of Things"
    assert e.doi == "10.1000/xyz"


def test_url_is_parsed():
    entries = parse_bib("@article{k, title={T}, url={https://www.sciencedirect.com/science/article/pii/S1}}")
    assert entries[0].url.endswith("/pii/S1")


def test_sources_come_from_annotation_and_from_url():
    text = """
% [3/70] PDF: a.pdf - TO DOWNLOAD (sources: scopus;wos)
@article{a2016,
  title = {A},
  doi = {10.1038/x},
}

@article{b2017,
  title = {B},
  url = {https://www.sciencedirect.com/science/article/pii/S1},
}

@article{c2018, title = {C}, doi = {10.1109/abc}}
"""
    a, b, c = parse_bib(text)
    assert a.sources == ("scopus", "wos")
    assert b.sources == ("sciencedirect",)
    assert c.sources == ("ieee",)


def test_journal_is_kept():
    (e,) = parse_bib("@article{a, title={T}, journal={Acta Tropica}}")
    assert e.journal == "Acta Tropica"


NBIB = """PMID- 37838744
OWN - NLM
STAT- MEDLINE
DP  - 2023 Oct 14
TI  - Early biomarkers for prediction of severe manifestations of dengue fever: a
      systematic review and a meta-analysis.
PG  - 17485
LID - 10.1038/s41598-023-44559-9 [doi]
LID - 17485
FAU - Rahman, Mizanur
AU  - Rahman M
FAU - Silva, Ana
AU  - Silva A
JT  - Scientific reports

PMID- 11111111
TI  - Second record
DP  - 2019
AID - 10.1000/xyz [doi]
"""


def test_nbib_records_become_entries():
    from paper_downloader.bib import parse_nbib

    first, second = parse_nbib(NBIB)
    assert first.key == "pmid37838744"
    assert first.title == "Early biomarkers for prediction of severe manifestations of dengue fever: a systematic review and a meta-analysis."
    assert first.doi == "10.1038/s41598-023-44559-9"
    assert first.year == "2023" and first.journal == "Scientific reports"
    assert first.authors == "Rahman, Mizanur and Silva, Ana"
    assert first.url == "https://pubmed.ncbi.nlm.nih.gov/37838744/"
    assert first.sources == ("pubmed",)
    assert (second.doi, second.year) == ("10.1000/xyz", "2019")


def test_only_bib_and_nbib_are_accepted():
    import pytest

    from paper_downloader.bib import parse_references

    assert len(parse_references(NBIB, "pubmed-export.NBIB")) == 2
    assert len(parse_references("@article{a, title={T}}", "refs.bib")) == 1
    for name in ("refs.ris", "refs.csv", "noext"):
        with pytest.raises(ValueError, match="Only .bib and .nbib"):
            parse_references(NBIB, name)
