"""Create account / log in / log out / who am I.

- Passwords: argon2id (argon2-cffi defaults), random salt per hash. Never stored or logged in plain text.
- Sessions: random 256-bit token in an httpOnly, SameSite=Lax cookie. Only its SHA-256 is stored. A session
  lasts 30 days from last use (sliding) or until log out.
- Login failures are rate limited per username and per client address.
- Login errors never say whether the username exists.
"""

from __future__ import annotations

import hashlib
import os
import re
import secrets
import time
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator

import reset_delivery
import store

router = APIRouter(prefix="/api/auth", tags=["auth"])

COOKIE = "session"
SESSION_DAYS = 30
APP_URL = os.getenv("APP_URL", "http://localhost:5200").rstrip("/")
RESET_MINUTES = 30
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"  # must be true when served over https

hasher = PasswordHasher()  # argon2id
_DUMMY_HASH = hasher.hash("timing-equalizer-not-a-real-password")

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,30}$")
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")
_CTRL = re.compile(r"[\x00-\x1f\x7f]")


def _clean(v: str) -> str:
    return _CTRL.sub("", v).strip()


class RegisterBody(BaseModel):
    first_name: str = Field(min_length=1, max_length=60)
    email: str = Field(max_length=254)
    username: str
    password: str = Field(min_length=10, max_length=128)

    @field_validator("first_name")
    @classmethod
    def name_ok(cls, v: str) -> str:
        v = _clean(v)
        if not v:
            raise ValueError("required")
        return v

    @field_validator("email")
    @classmethod
    def email_ok(cls, v: str) -> str:
        v = _clean(v).lower()
        if not EMAIL_RE.match(v):
            raise ValueError("Enter a valid email address")
        return v

    @field_validator("username")
    @classmethod
    def username_ok(cls, v: str) -> str:
        v = _clean(v)
        if not USERNAME_RE.match(v):
            raise ValueError("Username must be 3-30 characters: letters, numbers, . _ -")
        return v


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=60)
    password: str = Field(min_length=1, max_length=128)


class ForgotBody(BaseModel):
    email: str = Field(max_length=254)

    @field_validator("email")
    @classmethod
    def email_ok(cls, v: str) -> str:
        v = _clean(v).lower()
        if not EMAIL_RE.match(v):
            raise ValueError("Enter a valid email address")
        return v


class ResetBody(BaseModel):
    token: str = Field(min_length=20, max_length=100)
    password: str = Field(min_length=10, max_length=128)


class UserOut(BaseModel):
    first_name: str
    username: str


# ---------- login throttling (in memory; resets on restart) ----------

_MAX_FAILS, _WINDOW = 5, 15 * 60
_fails: dict[str, list[float]] = {}


def _locked(key: str) -> bool:
    now = time.time()
    recent = [t for t in _fails.get(key, []) if now - t < _WINDOW]
    _fails[key] = recent
    return len(recent) >= _MAX_FAILS


def _fail(*keys: str) -> None:
    for k in keys:
        _fails.setdefault(k, []).append(time.time())


# ---------- sessions ----------


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _start_session(response: Response, user_id: int) -> None:
    token = secrets.token_urlsafe(32)
    expires = _now() + timedelta(days=SESSION_DAYS)
    with store.connect() as conn:
        conn.execute("INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)", (_hash_token(token), user_id, _iso(expires)))
        conn.execute("DELETE FROM sessions WHERE expires_at < ?", (_iso(_now()),))
    response.set_cookie(COOKIE, token, max_age=SESSION_DAYS * 86400, httponly=True, samesite="lax", secure=COOKIE_SECURE, path="/")


def current_user(request: Request) -> dict:
    """Dependency: the logged-in user from the session cookie, or 401."""
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(401, "Not logged in")
    th = _hash_token(token)
    with store.connect() as conn:
        row = conn.execute(
            "SELECT u.id, u.first_name, u.username FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token_hash = ? AND s.expires_at > ?",
            (th, _iso(_now())),
        ).fetchone()
        if row is None:
            raise HTTPException(401, "Not logged in")
        conn.execute("UPDATE sessions SET expires_at = ? WHERE token_hash = ?", (_iso(_now() + timedelta(days=SESSION_DAYS)), th))
    return dict(row)


# ---------- routes ----------


@router.post("/register", response_model=UserOut, status_code=201)
def register(body: RegisterBody, response: Response) -> UserOut:
    pw_hash = hasher.hash(body.password)
    username = body.username.lower()
    with store.connect() as conn:
        if conn.execute("SELECT 1 FROM users WHERE username = ? OR email = ?", (username, body.email)).fetchone():
            raise HTTPException(409, "That username or email is already in use")  # one message so emails can't be probed
        cur = conn.execute("INSERT INTO users (first_name, email, username, password_hash) VALUES (?, ?, ?, ?)", (body.first_name, body.email, username, pw_hash))
        user_id = cur.lastrowid
        conn.execute("INSERT INTO profiles (user_id) VALUES (?)", (user_id,))
    _start_session(response, user_id)
    return UserOut(first_name=body.first_name, username=username)


@router.post("/login", response_model=UserOut)
def login(body: LoginBody, request: Request, response: Response) -> UserOut:
    username = body.username.strip().lower()
    ip = request.client.host if request.client else "unknown"
    ukey, ikey = f"u:{username}", f"ip:{ip}"
    if _locked(ukey) or _locked(ikey):
        raise HTTPException(429, "Too many failed attempts. Try again in 15 minutes.")
    with store.connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    stored = row["password_hash"] if row else _DUMMY_HASH  # always verify once so timing doesn't reveal the username
    try:
        ok = hasher.verify(stored, body.password)
    except (VerificationError, InvalidHashError):
        ok = False
    if not ok or row is None:
        _fail(ukey, ikey)
        raise HTTPException(401, "Invalid username or password")
    _fails.pop(ukey, None)
    if hasher.check_needs_rehash(row["password_hash"]):
        with store.connect() as conn:
            conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hasher.hash(body.password), row["id"]))
    _start_session(response, row["id"])
    return UserOut(first_name=row["first_name"], username=row["username"])


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response) -> None:
    token = request.cookies.get(COOKIE)
    if token:
        with store.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_hash_token(token),))
    response.delete_cookie(COOKIE, path="/")


@router.get("/me", response_model=UserOut)
def me(user: dict = Depends(current_user)) -> UserOut:
    return UserOut(first_name=user["first_name"], username=user["username"])


# ---------- forgotten password ----------

FORGOT_MESSAGE = (
    "If that email has an account, a reset link was created. This app runs on your own computer and sends no email, "
    "so the link appears in the terminal window where the app's backend is running. It works once and expires in 30 minutes."
)


@router.post("/forgot")
def forgot(body: ForgotBody, request: Request) -> dict:
    """Start a password reset. The answer is the same whether or not the email has an account, so emails can't be probed."""
    ip = request.client.host if request.client else "unknown"
    ekey, ikey = f"forgot-e:{body.email}", f"forgot-ip:{ip}"
    if _locked(ekey) or _locked(ikey):
        raise HTTPException(429, "Too many requests. Try again in 15 minutes.")
    _fail(ekey, ikey)  # every request counts, existing account or not
    token = secrets.token_urlsafe(32)
    token_hash = _hash_token(token)
    with store.connect() as conn:
        conn.execute("DELETE FROM password_resets WHERE expires_at < ?", (_iso(_now()),))
        row = conn.execute("SELECT id, username FROM users WHERE email = ?", (body.email,)).fetchone()
        if row is not None:
            conn.execute("DELETE FROM password_resets WHERE user_id = ?", (row["id"],))  # an older link stops working
            conn.execute("INSERT INTO password_resets (token_hash, user_id, expires_at) VALUES (?, ?, ?)", (token_hash, row["id"], _iso(_now() + timedelta(minutes=RESET_MINUTES))))
    if row is not None:
        reset_delivery.deliver(row["username"], f"{APP_URL}/?reset={token}")
    return {"message": FORGOT_MESSAGE}


@router.post("/reset")
def reset(body: ResetBody, request: Request) -> dict:
    """Set a new password with a valid, unused, unexpired link. Signs the account out everywhere."""
    ip = request.client.host if request.client else "unknown"
    ikey = f"reset-ip:{ip}"
    if _locked(ikey):
        raise HTTPException(429, "Too many attempts. Try again in 15 minutes.")
    token_hash = _hash_token(body.token)
    with store.connect() as conn:
        row = conn.execute("SELECT r.user_id, u.username FROM password_resets r JOIN users u ON u.id = r.user_id WHERE r.token_hash = ? AND r.expires_at > ?", (token_hash, _iso(_now()))).fetchone()
    if row is None:
        _fail(ikey)
        raise HTTPException(400, "This reset link is invalid or has expired. Ask for a new one.")
    new_hash = hasher.hash(body.password)
    with store.connect() as conn:
        used = conn.execute("DELETE FROM password_resets WHERE token_hash = ?", (token_hash,)).rowcount  # one use only
        if not used:
            raise HTTPException(400, "This reset link is invalid or has expired. Ask for a new one.")
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, row["user_id"]))
        conn.execute("DELETE FROM password_resets WHERE user_id = ?", (row["user_id"],))
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (row["user_id"],))  # anyone signed in with the old password is signed out
    _fails.pop(f"u:{row['username']}", None)  # a locked-out user can sign in with the new password
    return {"ok": True}
