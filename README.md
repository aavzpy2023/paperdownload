# Paper Downloader

FastAPI + React UI that takes a `.bib` file and downloads every article from
ScienceDirect (default), PubMed or EBSCO Research (experimental) using your own Chrome session.

## Run

    make up         # backend + nginx + React build in Docker, served on http://localhost:81

First login: `admin` / `admin` (override with `PD_ADMIN_USER` / `PD_ADMIN_PASSWORD` before the
first start, and change it in the Users page). Users live in `data/users.db`; the JWT secret in
`data/secret.key` (or `PD_SECRET_KEY`). Admins manage users at `/users`.

Roles:
- `admin` / `user`: a private Chrome with a persistent profile (`data/profiles/<id>/`), so publisher logins are kept between visits. Downloads go to `downloads/<id>-<username>/`.
- `guest`: a private Chrome with a throw-away profile and download folder, deleted on sign-out (or after 30 idle minutes). Each guest login is isolated from the others.

Each active person gets their own virtual desktop and Chrome, shown in the "Remote browser" tab
(noVNC behind nginx, authorized by the login cookie). Up to `PD_MAX_SESSIONS` (default 6) at once;
desktops of idle named users are stopped after 2 hours (profiles are kept).

`PD_START_URL` sets a default institution/library page; each person can override it in Settings.

Frontend development: `make dev-frontend` (Vite on :5173, proxies `/api` to :8000).

1. Press "Open <database>" (or "Open articles"): the remote browser opens only for the check. Sign in to the database with its "institutional access" option (or set your library/proxy URL in Settings), log in through your institution and open the search page of the site chosen in the "Site" selector (the tab title must contain the site name).
2. Back in Downloads, load the `.bib` and press Start (the app drives the tab you prepared).
   If selectors fail, press "Dump site page HTML" and inspect `debug/<site>_HHMMSS.html`.
3. The table shows done / pending / failed with the reason; use "Download ZIP" to fetch the PDFs.

Site selectors live in `paper_downloader/sciencedirect.py`, `paper_downloader/ebsco.py` and `paper_downloader/pubmed.py`; adjust them if the site changes.
