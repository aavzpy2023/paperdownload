import hashlib
import hmac
import os
import secrets
import sqlite3
import time
import uuid
from pathlib import Path

import jwt

DATA_DIR = Path(os.environ.get("PD_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
DB_PATH = DATA_DIR / "users.db"
SECRET_PATH = DATA_DIR / "secret.key"
TOKEN_TTL = 12 * 3600
ROLES = ("admin", "user", "guest")

_SCRYPT = {"n": 2**14, "r": 8, "p": 1}


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, digest = stored.split("$")
        candidate = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), **_SCRYPT)
    except ValueError:
        return False
    return hmac.compare_digest(candidate.hex(), digest)


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _public(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    return {
        "id": row["id"], "username": row["username"], "role": row["role"], "active": bool(row["active"]),
        "institution_url": row["institution_url"],
    }


def init_db() -> None:
    """Create the schema and seed a first admin so the UI is reachable on a fresh install."""
    with _connect() as c:
        c.execute(
            "CREATE TABLE IF NOT EXISTS users ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL COLLATE NOCASE, "
            "password_hash TEXT NOT NULL, role TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, "
            "institution_url TEXT NOT NULL DEFAULT '')"
        )
        if "institution_url" not in {r["name"] for r in c.execute("PRAGMA table_info(users)")}:
            c.execute("ALTER TABLE users ADD COLUMN institution_url TEXT NOT NULL DEFAULT ''")
        if c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
            c.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'admin')",
                (
                    os.environ.get("PD_ADMIN_USER", "admin"),
                    hash_password(os.environ.get("PD_ADMIN_PASSWORD", "admin")),
                ),
            )


def _secret() -> str:
    if env := os.environ.get("PD_SECRET_KEY"):
        return env
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not SECRET_PATH.exists():
        SECRET_PATH.write_text(secrets.token_hex(32))
        SECRET_PATH.chmod(0o600)
    return SECRET_PATH.read_text().strip()


def make_token(user: dict) -> str:
    """Each login gets its own session id (sid); guests use it to keep their workspaces apart."""
    claims = {"sub": str(user["id"]), "sid": uuid.uuid4().hex, "exp": int(time.time()) + TOKEN_TTL}
    return jwt.encode(claims, _secret(), algorithm="HS256")


def user_from_token(token: str) -> dict | None:
    """Resolve the token to a user fresh from the DB, so deactivation/role changes apply at once."""
    try:
        claims = jwt.decode(token, _secret(), algorithms=["HS256"])
        uid, sid = int(claims["sub"]), str(claims["sid"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
    user = get_user(uid)
    return {**user, "sid": sid} if user and user["active"] else None


def authenticate(username: str, password: str) -> dict | None:
    with _connect() as c:
        row = c.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if row is None or not row["active"] or not verify_password(password, row["password_hash"]):
        return None
    return _public(row)


def get_user(user_id: int) -> dict | None:
    with _connect() as c:
        return _public(c.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())


def list_users() -> list[dict]:
    with _connect() as c:
        return [_public(r) for r in c.execute("SELECT * FROM users ORDER BY username")]


def create_user(username: str, password: str, role: str) -> dict:
    """Raises ValueError on a duplicate username."""
    try:
        with _connect() as c:
            cur = c.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                (username, hash_password(password), role),
            )
    except sqlite3.IntegrityError:
        raise ValueError("Username already exists") from None
    return get_user(cur.lastrowid)


def _other_active_admins(c: sqlite3.Connection, user_id: int) -> int:
    return c.execute(
        "SELECT COUNT(*) FROM users WHERE role = 'admin' AND active = 1 AND id != ?", (user_id,)
    ).fetchone()[0]


def update_user(user_id: int, *, password: str | None, role: str | None, active: bool | None) -> dict | None:
    """Raises ValueError if the change would leave no active admin."""
    with _connect() as c:
        row = c.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            return None
        new_role = role or row["role"]
        new_active = row["active"] if active is None else int(active)
        if row["role"] == "admin" and (new_role != "admin" or not new_active) and not _other_active_admins(c, user_id):
            raise ValueError("At least one active admin is required")
        c.execute(
            "UPDATE users SET role = ?, active = ?, password_hash = ? WHERE id = ?",
            (new_role, new_active, hash_password(password) if password else row["password_hash"], user_id),
        )
    return get_user(user_id)


def set_institution_url(user_id: int, url: str) -> dict | None:
    with _connect() as c:
        c.execute("UPDATE users SET institution_url = ? WHERE id = ?", (url, user_id))
    return get_user(user_id)


def delete_user(user_id: int) -> bool:
    """Raises ValueError when deleting the last active admin."""
    with _connect() as c:
        row = c.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            return False
        if row["role"] == "admin" and row["active"] and not _other_active_admins(c, user_id):
            raise ValueError("At least one active admin is required")
        c.execute("DELETE FROM users WHERE id = ?", (user_id,))
    return True
