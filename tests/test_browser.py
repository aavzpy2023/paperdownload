import socket
import stat
import threading

import pytest

from paper_downloader import browser

FAKE_CHROME = """#!/usr/bin/env python3
import http.server, sys, time
port = int([a for a in sys.argv if a.startswith("--remote-debugging-port=")][0].split("=")[1])
open(sys.argv[0] + ".started", "a").write("x")
time.sleep(1.5)  # a loaded machine brings Chrome up slowly

class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self): self.send_response(200); self.end_headers(); self.wfile.write(b"{}")
    do_PUT = do_GET
    def log_message(self, *a): pass

http.server.HTTPServer(("127.0.0.1", port), H).serve_forever()
"""


@pytest.fixture
def fake_chrome(tmp_path, monkeypatch):
    script = tmp_path / "chrome"
    script.write_text(FAKE_CHROME)
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setattr(browser, "_chrome_bin", lambda: str(script))
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    chrome = browser.Chrome(tmp_path / "profile", port)
    yield chrome, script
    chrome.close()


def test_launch_clears_stale_profile_locks(fake_chrome):
    chrome, _ = fake_chrome
    chrome.work_dir.mkdir()
    lock = chrome.work_dir / "SingletonLock"
    lock.symlink_to("host-1234")

    chrome.launch()

    assert not lock.exists() and not lock.is_symlink()
    assert chrome.debugger_up()


def test_concurrent_launches_start_a_single_chrome(fake_chrome):
    chrome, script = fake_chrome
    threads = [threading.Thread(target=chrome.launch) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert (script.parent / "chrome.started").read_text() == "x"
