"""Filtering HTTP proxy for the remote browsers.

Chrome runs next to the app's own services (the backend API, other people's debugging ports and
remote screens). Every request it makes goes through this proxy, which refuses any destination
that is not a public internet address, so a person in the remote browser can reach publishers and
their institution but not this machine, the Docker network or the local network.
"""

import asyncio
import ipaddress
import logging
import os
import threading
from urllib.parse import urlsplit

log = logging.getLogger(__name__)
MAX_HEADER_BYTES = 64 * 1024
CONNECT_TIMEOUT_S = 20


def allow_private() -> bool:
    return os.environ.get("PD_ALLOW_PRIVATE_HOSTS") == "1"


async def resolve_public(host: str, port: int) -> str | None:
    """First address of `host` if every address it resolves to is public, else None."""
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=1)
    except OSError:
        return None
    addresses = {info[4][0] for info in infos}
    if not addresses:
        return None
    if not allow_private() and not all(ipaddress.ip_address(a.split("%")[0]).is_global for a in addresses):
        return None
    return sorted(addresses)[0]


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
    except (ConnectionError, asyncio.CancelledError):
        pass
    finally:
        try:
            writer.close()
        except RuntimeError:
            pass


async def _refuse(writer: asyncio.StreamWriter, status: str = "403 Forbidden") -> None:
    writer.write(f"HTTP/1.1 {status}\r\nConnection: close\r\nContent-Length: 0\r\n\r\n".encode())
    try:
        await writer.drain()
    finally:
        writer.close()


async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=30)
    except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, asyncio.TimeoutError, ConnectionError):
        writer.close()
        return
    if len(head) > MAX_HEADER_BYTES:
        return await _refuse(writer, "431 Request Header Fields Too Large")
    request_line, _, rest = head.partition(b"\r\n")
    try:
        method, target, version = request_line.decode("latin-1").split(" ", 2)
        if method.upper() == "CONNECT":
            host, _, port_text = target.rpartition(":")
            host, port, first_bytes = host.strip("[]"), int(port_text), b""
        else:
            url = urlsplit(target)
            if url.scheme != "http" or not url.hostname:
                return await _refuse(writer, "400 Bad Request")
            host, port = url.hostname, url.port or 80
            path = (url.path or "/") + (f"?{url.query}" if url.query else "")
            headers = [h for h in rest.split(b"\r\n") if h and not h.lower().startswith((b"proxy-", b"connection:"))]
            first_bytes = b"\r\n".join([f"{method} {path} {version}".encode("latin-1"), *headers, b"Connection: close", b"", b""])
    except ValueError:
        return await _refuse(writer, "400 Bad Request")

    address = await resolve_public(host, port)
    if address is None:
        log.warning("egress proxy refused %s:%s", host, port)
        return await _refuse(writer)
    try:
        up_reader, up_writer = await asyncio.wait_for(asyncio.open_connection(address, port), timeout=CONNECT_TIMEOUT_S)
    except (OSError, asyncio.TimeoutError):
        return await _refuse(writer, "502 Bad Gateway")

    if method.upper() == "CONNECT":
        writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        await writer.drain()
    else:
        up_writer.write(first_bytes)
        await up_writer.drain()
    await asyncio.gather(_pipe(reader, up_writer), _pipe(up_reader, writer))


def start(port: int, host: str = "127.0.0.1") -> threading.Thread:
    """Run the proxy on its own event loop in a daemon thread; returns once it is listening."""
    ready = threading.Event()

    def run() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(asyncio.start_server(handle, host, port, limit=MAX_HEADER_BYTES))
        ready.set()
        loop.run_forever()

    thread = threading.Thread(target=run, name="egress-proxy", daemon=True)
    thread.start()
    ready.wait(10)
    return thread
