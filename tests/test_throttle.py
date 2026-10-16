import threading
import time

from paper_downloader.bib import Entry
from paper_downloader.throttle import Throttle, publisher_key, url_key


def test_requests_to_one_publisher_are_spaced_but_others_are_not():
    t = Throttle(gap=(0.3, 0.3))
    start = time.monotonic()
    assert t.acquire("10.1016") == "ok"
    assert t.acquire("10.3390") == "ok"
    assert time.monotonic() - start < 0.2

    assert t.acquire("10.1016") == "ok"
    assert time.monotonic() - start >= 0.3


def test_cooldown_refuses_instead_of_blocking_and_clear_lifts_it():
    t = Throttle(gap=(0.0, 0.0))
    t.cool_down("10.1016", seconds=1000)
    started = time.monotonic()
    assert t.acquire("10.1016", max_wait=5) == "cooldown"
    assert time.monotonic() - started < 0.5

    t.clear("10.1016")
    assert t.acquire("10.1016") == "ok"


def test_stop_interrupts_the_wait():
    t = Throttle(gap=(30.0, 30.0))
    t.acquire("k")
    stop = threading.Event()
    threading.Timer(0.2, stop.set).start()
    started = time.monotonic()
    assert t.acquire("k", stop) == "stopped"
    assert time.monotonic() - started < 2


def test_keys_match_between_entries_and_doi_links():
    entry = Entry("a", "A", "", "", "https://doi.org/10.1016/j.x.1", "")
    assert publisher_key(entry) == "10.1016"
    assert url_key("https://doi.org/10.1016/j.x.1") == "10.1016"
    assert publisher_key(Entry("b", "B", "", "", "", "https://www.scopus.com/x")) == "www.scopus.com"
