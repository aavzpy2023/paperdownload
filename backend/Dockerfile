FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends wget ca-certificates xvfb x11vnc fluxbox novnc websockify \
    && wget -q -O /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get install -y --no-install-recommends /tmp/chrome.deb \
    && rm -rf /tmp/chrome.deb /var/lib/apt/lists/*

# Chrome must never offer to remember the passwords people type into publisher sites.
RUN mkdir -p /etc/opt/chrome/policies/managed \
    && echo '{"PasswordManagerEnabled": false, "AutofillCreditCardEnabled": false, "AutofillAddressEnabled": false}' \
    > /etc/opt/chrome/policies/managed/paper-downloader.json

WORKDIR /app
COPY pyproject.toml .
RUN python -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']))" \
    | pip install --no-cache-dir -r /dev/stdin
COPY paper_downloader ./paper_downloader

ENV HOME=/home/pd PYTHONPATH=/app PYTHONUNBUFFERED=1 PD_CHROME_NO_SANDBOX=1
RUN useradd -u 1000 -m -d /home/pd pd \
    && mkdir -p /tmp/.X11-unix /app/data /app/downloads /app/debug \
    && chmod 1777 /tmp/.X11-unix \
    && chown -R pd:pd /app/data /app/downloads /app/debug /home/pd
USER pd
CMD ["uvicorn", "paper_downloader.server:app", "--host", "0.0.0.0", "--port", "8000"]
