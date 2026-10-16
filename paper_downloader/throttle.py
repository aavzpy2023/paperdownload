import random
import threading
import time
from urllib.parse import urlparse

from .bib import Entry, clean_doi

GAP = (10.0, 20.0)  # seconds between two requests to the same publisher, across all users
COOLDOWN_S = 600.0  # back-off for a publisher that showed a human check mid-run


class Throttle:
    """Spaces out requests per publisher for every user sharing this server's IP."""

    def __init__(self, gap: tuple[float, float] = GAP, clock=time.monotonic) -> None:
        self._gap = gap
        self._clock = clock
        self._lock = threading.Lock()
        self._next: dict[str, float] = {}

    def acquire(self, key: str, stop: threading.Event | None = None, max_wait: float = 120.0) -> str:
        """Wait for this publisher's next free slot: "ok", "stopped" (stop was set) or "cooldown".

        Slots are reserved in order, so several waiters queue up instead of bursting together.
        """
        with self._lock:
            now = self._clock()
            wait = max(0.0, self._next.get(key, 0.0) - now)
            if wait > max_wait:
                return "cooldown"
            self._next[key] = now + wait + random.uniform(*self._gap)
        if wait > 0:
            if stop is not None:
                return "stopped" if stop.wait(wait) else "ok"
            time.sleep(wait)
        return "ok"

    def cool_down(self, key: str, seconds: float = COOLDOWN_S) -> None:
        with self._lock:
            self._next[key] = max(self._next.get(key, 0.0), self._clock() + seconds)

    def clear(self, key: str) -> None:
        """Lift a back-off once a person has solved the check by hand."""
        with self._lock:
            self._next.pop(key, None)

    def remaining(self, key: str) -> float:
        with self._lock:
            return max(0.0, self._next.get(key, 0.0) - self._clock())


def publisher_key(entry: Entry, fallback: str = "") -> str:
    doi = clean_doi(entry.doi)
    return doi.split("/")[0] if doi else urlparse(entry.url).netloc or fallback


def url_key(url: str) -> str:
    """Same key for a doi.org link as for the entry it came from (the DOI prefix)."""
    parsed = urlparse(url)
    if parsed.netloc.endswith("doi.org"):
        return parsed.path.lstrip("/").split("/")[0]
    return parsed.netloc


throttle = Throttle()
