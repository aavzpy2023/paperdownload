import asyncio
import socket
import threading

import pytest

from paper_downloader import egress, workspace
from paper_downloader.job import Job


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def proxy_port():
    port = free_port()
    egress.start(port)
    return port


@pytest.fixture
def web_server():
    """A tiny local HTTP server standing in for an internal service."""
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(5)

    def serve():
        while True:
            try:
                conn, _ = server.accept()
            except OSError:
                return
            conn.recv(4096)
            conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 6\r\nConnection: close\r\n\r\nsecret")
            conn.close()

    threading.Thread(target=serve, daemon=True).start()
    yield server.getsockname()[1]
    server.close()


def ask(proxy_port: int, request: bytes) -> bytes:
    with socket.create_connection(("127.0.0.1", proxy_port), timeout=10) as s:
        s.sendall(request)
        chunks = []
        while data := s.recv(65536):
            chunks.append(data)
        return b"".join(chunks)


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "10.0.0.5", "192.168.1.1", "169.254.169.254", "172.17.0.2", "[::1]"])
def test_connect_to_internal_hosts_is_refused(proxy_port, host):
    reply = ask(proxy_port, f"CONNECT {host}:8000 HTTP/1.1\r\nHost: {host}:8000\r\n\r\n".encode())
    assert reply.startswith(b"HTTP/1.1 403")


def test_plain_http_to_loopback_is_refused_and_never_reaches_the_service(proxy_port, web_server):
    reply = ask(proxy_port, f"GET http://127.0.0.1:{web_server}/ HTTP/1.1\r\nHost: 127.0.0.1:{web_server}\r\n\r\n".encode())
    assert reply.startswith(b"HTTP/1.1 403") and b"secret" not in reply


def test_private_destinations_work_only_when_explicitly_allowed(proxy_port, web_server, monkeypatch):
    monkeypatch.setenv("PD_ALLOW_PRIVATE_HOSTS", "1")
    reply = ask(proxy_port, f"GET http://127.0.0.1:{web_server}/ HTTP/1.1\r\nHost: x\r\nProxy-Connection: keep-alive\r\n\r\n".encode())
    assert reply.startswith(b"HTTP/1.1 200") and reply.endswith(b"secret")


@pytest.mark.parametrize("address, public", [
    ("8.8.8.8", True), ("1.1.1.1", True),
    ("10.1.2.3", False), ("127.0.0.1", False), ("169.254.169.254", False), ("100.64.0.1", False), ("::1", False),
])
def test_only_global_addresses_pass(address, public):
    result = asyncio.run(egress.resolve_public(address, 443))
    assert (result is not None) is public


def test_closed_browser_is_relaunched_while_the_view_is_open(tmp_path):
    class FakeProc:
        def poll(self):
            return 0  # exited

    class FakeChrome:
        proc = FakeProc()
        launched: list = []

        def debugger_up(self):
            return False

        def launch(self, url=None):
            self.launched.append(url)

    manager = workspace.Manager()
    ws = workspace.Workspace("user:1", False, tmp_path, Job(out_dir=tmp_path), viewer_on=True)
    ws.job.chrome = FakeChrome()
    manager._spaces[ws.key] = ws

    manager.revive_closed_browsers()
    assert FakeChrome.launched == ["about:blank"]

    ws.viewer_on = False  # no view open: leave the browser closed
    manager.revive_closed_browsers()
    assert FakeChrome.launched == ["about:blank"]
