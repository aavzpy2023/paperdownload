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
