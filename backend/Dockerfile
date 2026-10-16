FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends wget ca-certificates xvfb x11vnc fluxbox novnc websockify \
    && wget -q -O /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get install -y --no-install-recommends /tmp/chrome.deb \
    && rm -rf /tmp/chrome.deb /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml .
RUN python -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']))" \
    | pip install --no-cache-dir -r /dev/stdin

ENV HOME=/home/pd PYTHONPATH=/app PYTHONUNBUFFERED=1 PD_CHROME_NO_SANDBOX=1
RUN mkdir -p /home/pd /tmp/.X11-unix && chmod 777 /home/pd && chmod 1777 /tmp/.X11-unix
CMD ["uvicorn", "paper_downloader.server:app", "--host", "127.0.0.1", "--port", "8000"]
