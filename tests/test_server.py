import pytest
from fastapi.testclient import TestClient

from paper_downloader import auth, server, workspace


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "DATA_DIR", tmp_path)
    monkeypatch.setattr(auth, "DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(auth, "SECRET_PATH", tmp_path / "secret.key")
    monkeypatch.setattr(workspace, "ROOT", tmp_path)
    monkeypatch.setattr(workspace.manager, "_spaces", {})
    monkeypatch.setattr(workspace.manager, "_start_desktop", lambda ws: None)
    monkeypatch.setattr(workspace.manager, "_start_viewer", lambda ws: None)
    with TestClient(server.app) as c:
        yield c


def login(client, username="admin", password="admin"):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    return {"Authorization": f"Bearer {r.json()['token']}"} if r.status_code == 200 else None


def test_api_requires_token(client):
    assert client.get("/api/state").status_code == 401
    assert client.get("/api/users").status_code == 401


def test_login_rejects_bad_password(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "nope"})
    assert r.status_code == 401


def test_admin_manages_users(client):
    h = login(client)
    r = client.post("/api/users", json={"username": "ana", "password": "secret1", "role": "user"}, headers=h)
    assert r.status_code == 201
    uid = r.json()["id"]
    assert client.post("/api/users", json={"username": "ANA", "password": "secret1"}, headers=h).status_code == 409

    ana = login(client, "ana", "secret1")
    assert client.get("/api/state", headers=ana).status_code == 200
    assert client.get("/api/users", headers=ana).status_code == 403

    client.patch(f"/api/users/{uid}", json={"active": False}, headers=h)
    assert client.get("/api/state", headers=ana).status_code == 401
    assert login(client, "ana", "secret1") is None

    assert client.delete(f"/api/users/{uid}", headers=h).status_code == 204


def test_cannot_remove_last_admin(client):
    h = login(client)
    admin_id = client.get("/api/auth/me", headers=h).json()["id"]
    assert client.delete(f"/api/users/{admin_id}", headers=h).status_code == 409
    assert client.patch(f"/api/users/{admin_id}", json={"role": "user"}, headers=h).status_code == 409


def add_user(client, h, username, role):
    client.post("/api/users", json={"username": username, "password": "secret1", "role": role}, headers=h)
    return login(client, username, "secret1")


def test_guest_cannot_manage_users(client):
    g = add_user(client, login(client), "visitor", "guest")
    assert client.get("/api/state", headers=g).status_code == 200
    assert client.get("/api/users", headers=g).status_code == 403


def test_workspaces_are_isolated_per_user_and_per_guest_login(client):
    admin = login(client)
    ana = add_user(client, admin, "ana", "user")
    g1 = add_user(client, admin, "visitor", "guest")
    g2 = login(client, "visitor", "secret1")

    for h in (admin, ana, g1, g2):
        client.get("/api/state", headers=h)
    spaces = workspace.manager._spaces
    assert len(spaces) == 4
    assert sum(k.startswith("guest:") for k in spaces) == 2
    assert spaces[next(k for k in spaces if k.startswith("guest:"))].profile_dir.parent != auth.DATA_DIR / "profiles"


def test_vnc_auth_needs_a_running_session_and_cookie_works(client):
    h = login(client)
    assert client.get("/api/vnc/auth", headers=h).status_code == 403

    assert client.post("/api/session", headers=h).status_code == 200
    r = client.get("/api/vnc/auth")  # cookie set at login, no bearer header
    assert r.status_code == 200
    assert r.headers["x-vnc-port"] == "6100"


def test_sessions_are_capped(client, monkeypatch):
    monkeypatch.setattr(workspace, "MAX_SESSIONS", 1)
    admin = login(client)
    ana = add_user(client, admin, "ana", "user")
    assert client.post("/api/session", headers=admin).status_code == 200
    assert client.post("/api/session", headers=ana).status_code == 503


def test_guest_logout_discards_workspace(client):
    admin = login(client)
    g = add_user(client, admin, "visitor", "guest")
    client.post("/api/session", headers=g)
    ws = next(iter(workspace.manager._spaces.values()))
    ws.profile_dir.mkdir(parents=True)

    client.post("/api/auth/logout")
    assert not workspace.manager._spaces
    assert not ws.profile_dir.exists()


def test_named_user_workspace_survives_logout(client):
    admin = login(client)
    ana = add_user(client, admin, "ana", "user")
    client.post("/api/session", headers=ana)
    client.post("/api/auth/logout")
    assert any(k.startswith("user:") for k in workspace.manager._spaces)


def test_start_is_refused_until_access_is_verified(client, tmp_path):
    h = login(client)
    bib = b"@article{a, title={A}, doi={10.1016/x}}"
    client.post("/api/upload", files={"bib": ("r.bib", bib)}, headers=h)
    r = client.post("/api/start", json={"site": "other"}, headers=h)
    assert r.status_code == 409


def test_zip_contains_every_pdf_in_the_folder(client):
    import io
    import zipfile

    h = login(client)
    assert client.get("/api/zip", headers=h).status_code == 409

    client.post("/api/upload", files={"bib": ("refs.bib", b"@article{a, title={A}}")}, headers=h)
    ws = next(iter(workspace.manager._spaces.values()))
    ws.job.target.mkdir(parents=True, exist_ok=True)
    (ws.job.target / "a.pdf").write_bytes(b"%PDF-1")
    (ws.job.target / "b.pdf").write_bytes(b"%PDF-2")

    assert client.get("/api/state", headers=h).json()["pdf_count"] == 2
    r = client.get("/api/zip", headers=h)
    assert r.status_code == 200
    assert sorted(zipfile.ZipFile(io.BytesIO(r.content)).namelist()) == ["a.pdf", "b.pdf"]


def test_remote_view_exists_only_while_open(client):
    h = login(client)
    assert client.get("/api/vnc/auth", headers=h).status_code == 403
    client.post("/api/session", headers=h)
    assert client.get("/api/vnc/auth", headers=h).status_code == 200
    assert client.delete("/api/session", headers=h).status_code == 204
    assert client.get("/api/vnc/auth", headers=h).status_code == 403


def test_other_actions_do_not_open_the_remote_view(client):
    h = login(client)
    client.post("/api/preflight", json={"site": "other"}, headers=h)  # 409 (nothing pending), still starts the desktop
    assert client.get("/api/vnc/auth", headers=h).status_code == 403


def test_named_user_logout_closes_the_view_but_keeps_the_workspace(client):
    h = login(client)
    client.post("/api/session", headers=h)
    client.post("/api/auth/logout")
    assert any(k.startswith("user:") for k in workspace.manager._spaces)
    assert next(iter(workspace.manager._spaces.values())).viewer_on is False


def test_idle_remote_view_is_closed_by_the_reaper(client):
    h = login(client)
    client.post("/api/session", headers=h)
    ws = next(iter(workspace.manager._spaces.values()))
    ws.viewer_seen -= workspace.VIEWER_IDLE_SECONDS + 1
    workspace.manager.reap_idle()
    assert ws.viewer_on is False


def test_each_user_keeps_their_own_institution_url(client):
    admin = login(client)
    ana = add_user(client, admin, "ana", "user")
    assert client.get("/api/providers", headers=admin).json()["institution_url"] == ""

    r = client.patch("/api/auth/me", json={"institution_url": "https://library.example.edu"}, headers=ana)
    assert r.status_code == 200
    assert client.get("/api/providers", headers=ana).json()["institution_url"] == "https://library.example.edu"
    assert client.get("/api/providers", headers=admin).json()["institution_url"] == ""

    bad = client.patch("/api/auth/me", json={"institution_url": "javascript:alert(1)"}, headers=ana)
    assert bad.status_code == 422


def test_open_institution_page_needs_a_url(client):
    h = login(client)
    r = client.post("/api/open", json={}, headers=h)
    assert r.status_code == 400


def test_start_accepts_a_selection_mixing_databases_but_names_the_locked_ones(client):
    h = login(client)
    bib = b"@article{a, title={A}, doi={10.1016/x}}\n@article{b, title={B}, doi={10.1109/y}}"
    client.post("/api/upload", files={"bib": ("r.bib", bib)}, headers=h)

    r = client.post("/api/start", json={"sites": {"other": [0], "ieee": [1]}}, headers=h)
    assert r.status_code == 409
    assert "Other (by DOI)" in r.json()["detail"] and "IEEE Xplore" in r.json()["detail"]

    assert client.post("/api/start", json={"sites": {"nope": [0]}}, headers=h).status_code == 400


def test_upload_accepts_nbib_and_rejects_other_formats(client):
    h = login(client)
    nbib = b"PMID- 1\nTI  - A title\nDP  - 2020\nLID - 10.1/x [doi]\n"
    r = client.post("/api/upload", files={"bib": ("export.nbib", nbib)}, headers=h)
    assert r.status_code == 200 and r.json()["count"] == 1
    assert client.get("/api/state", headers=h).json()["rows"][0]["sources"] == ["pubmed"]

    bad = client.post("/api/upload", files={"bib": ("refs.ris", b"TY  - JOUR")}, headers=h)
    assert bad.status_code == 400


def test_only_admins_can_see_or_change_users(client):
    admin = login(client)
    user = add_user(client, admin, "ana", "user")
    guest = add_user(client, admin, "visitor", "guest")
    body = {"username": "zzz", "password": "secret1", "role": "admin", "active": False}

    for who in (user, guest):
        assert client.get("/api/users", headers=who).status_code == 403
        assert client.post("/api/users", json=body, headers=who).status_code == 403
        assert client.patch("/api/users/1", json=body, headers=who).status_code == 403
        assert client.delete("/api/users/1", headers=who).status_code == 403
        assert "password" not in client.get("/api/auth/me", headers=who).text

    client.cookies.clear()
    assert client.get("/api/users").status_code == 401
    assert [u["username"] for u in client.get("/api/users", headers=admin).json()] == ["admin", "ana", "visitor"]
