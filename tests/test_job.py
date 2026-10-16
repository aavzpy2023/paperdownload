from datetime import date

from paper_downloader.bib import Entry
from paper_downloader.job import DONE, PENDING, Job


def test_load_uses_dated_folder_and_restores_existing(tmp_path):
    job = Job(out_dir=tmp_path)
    folder = tmp_path / f"refs_{date.today():%Y%m%d}"
    folder.mkdir()
    (folder / "a2020.pdf").write_bytes(b"%PDF")
    entries = [Entry("a2020", "A", "", "2020", ""), Entry("b2021", "B", "", "2021", "")]

    job.load(entries, "refs.bib")

    assert job.target == folder
    assert [r.status for r in job.rows] == [DONE, PENDING]


def test_snapshot_can_zip_only_when_idle_with_done_rows(tmp_path):
    job = Job(out_dir=tmp_path)
    job.load([Entry("a", "A", "", "", "")], "refs.bib")
    assert not job.snapshot()["can_zip"]
    job.rows[0].status = DONE
    assert job.snapshot()["can_zip"]
    job.running = True
    assert not job.snapshot()["can_zip"]


def test_snapshot_picks_up_pdfs_added_by_hand(tmp_path):
    job = Job(out_dir=tmp_path)
    job.load([Entry("a2020", "A", "", "2020", "")], "refs.bib")
    job.rows[0].status = "failed"
    assert job.snapshot()["rows"][0]["status"] == "failed"

    job.target.mkdir(parents=True)
    (job.target / "a2020.pdf").write_bytes(b"%PDF")

    assert job.snapshot()["rows"][0]["status"] == "done"


def test_preflight_urls_pick_one_article_per_publisher(tmp_path):
    job = Job(out_dir=tmp_path)
    job.load([
        Entry("a", "A", "", "", "10.1016/x.1", "", ("wos",)),
        Entry("b", "B", "", "", "https://doi.org/10.1016/x.2", "", ("wos",)),
        Entry("c", "C", "", "", "10.3390/y", "", ("wos",)),
        Entry("d", "D", "", "", "10.1109/z", "", ("scopus",)),
        Entry("e", "E", "", "", "", "https://example.org/p", ("wos",)),
    ])
    assert job.preflight_urls("wos") == [
        "https://doi.org/10.1016/x.1", "https://doi.org/10.3390/y", "https://example.org/p",
    ]
    job.rows[0].status = DONE
    assert job.preflight_urls("wos")[0] == "https://doi.org/10.1016/x.2"


def test_snapshot_access_states(tmp_path):
    job = Job(out_dir=tmp_path)
    job.load([
        Entry("a", "A", "", "", "10.1016/x", "", ("wos",)),
        Entry("b", "B", "", "", "10.1109/z", "", ("ieee",)),
    ])
    assert job.snapshot()["access"] == {"wos": "required", "ieee": "required"}

    job.access_ok.add("wos")
    job.rows[1].status = DONE
    assert job.snapshot()["access"] == {"wos": "ok", "ieee": "none"}

    job.load([Entry("a", "A", "", "", "10.1016/x", "", ("wos",))])
    assert job.snapshot()["access"] == {"wos": "required"}


def test_only_one_verification_runs_at_a_time(tmp_path):
    import pytest

    job = Job(out_dir=tmp_path)
    job.load([Entry("a", "A", "", "", "10.1016/x", "", ("wos",))])
    job.chrome = object()
    job.verifying = "wos"
    with pytest.raises(RuntimeError, match="already in progress"):
        job.verify_access("wos")
    assert job.snapshot()["verifying"] == "wos"
