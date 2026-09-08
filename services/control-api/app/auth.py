from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field

from app.settings import get_settings

bearer = HTTPBearer(auto_error=False)
BROWSER_SESSION_COOKIE = "hermes_session"
BOOTSTRAP_TTL_SECONDS = 90
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _urlsafe(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


@dataclass(frozen=True, slots=True)
class BrowserSession:
    cookie: str
    csrf_token: str
    max_age: int


class BrowserBootstrapExchange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=32, max_length=128)


class BrowserSessionManager:
    """Mints one-use browser bootstraps and stateless signed local sessions."""

    def __init__(self, api_token: str, session_ttl_seconds: int) -> None:
        self._key = hmac.new(
            api_token.encode("utf-8"),
            b"hermes-browser-session-key-v1",
            hashlib.sha256,
        ).digest()
        self._session_ttl_seconds = session_ttl_seconds
        self._bootstraps: dict[str, float] = {}
        self._lock = threading.Lock()

    def _sign(self, purpose: bytes, value: str) -> str:
        return _urlsafe(
            hmac.new(self._key, purpose + value.encode("utf-8"), hashlib.sha256).digest()
        )

    def issue_bootstrap(self) -> str:
        code = secrets.token_urlsafe(32)
        digest = hashlib.sha256(code.encode("utf-8")).hexdigest()
        now = time.time()
        with self._lock:
            self._bootstraps = {
                key: expiry for key, expiry in self._bootstraps.items() if expiry > now
            }
            if len(self._bootstraps) >= 32:
                oldest = min(self._bootstraps, key=lambda key: self._bootstraps[key])
                self._bootstraps.pop(oldest, None)
            self._bootstraps[digest] = now + BOOTSTRAP_TTL_SECONDS
        return code

    def consume_bootstrap(self, code: str) -> BrowserSession:
        digest = hashlib.sha256(code.encode("utf-8")).hexdigest()
        now = time.time()
        with self._lock:
            expiry = self._bootstraps.pop(digest, None)
        if expiry is None or expiry <= now:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Browser bootstrap is invalid or expired",
            )
        session_expiry = int(now) + self._session_ttl_seconds
        nonce = secrets.token_urlsafe(24)
        payload = f"v1.{session_expiry}.{nonce}"
        cookie = f"{payload}.{self._sign(b'session:', payload)}"
        return BrowserSession(
            cookie=cookie,
            csrf_token=self._sign(b"csrf:", payload),
            max_age=self._session_ttl_seconds,
        )

    def validate_session(self, cookie: str) -> tuple[str, str]:
        try:
            version, expiry_text, nonce, signature = cookie.split(".", 3)
            expiry = int(expiry_text)
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Browser session required",
            ) from None
        payload = f"{version}.{expiry}.{nonce}"
        expected_signature = self._sign(b"session:", payload)
        if (
            version != "v1"
            or expiry <= int(time.time())
            or not hmac.compare_digest(signature, expected_signature)
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Browser session required",
            )
        return payload, self._sign(b"csrf:", payload)


_browser_sessions: BrowserSessionManager | None = None
_browser_sessions_lock = threading.Lock()


def get_browser_sessions() -> BrowserSessionManager:
    global _browser_sessions
    if _browser_sessions is None:
        with _browser_sessions_lock:
            if _browser_sessions is None:
                settings = get_settings()
                _browser_sessions = BrowserSessionManager(
                    settings.api_token, settings.dashboard_session_ttl_seconds
                )
    return _browser_sessions


def _valid_bearer(
    credentials: HTTPAuthorizationCredentials | None,
) -> bool:
    if credentials is None or credentials.scheme.lower() != "bearer":
        return False
    return hmac.compare_digest(credentials.credentials, get_settings().api_token)


def require_bearer_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required",
        )
    if not _valid_bearer(credentials):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid token")


def require_same_origin(request: Request) -> None:
    origin = request.headers.get("origin", "")
    parsed = urlsplit(origin)
    expected = f"{request.url.scheme}://{request.headers.get('host', '')}"
    supplied = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Origin rejected")


def require_api_token(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    if credentials is not None:
        require_bearer_token(credentials)
        return

    cookie = request.cookies.get(BROWSER_SESSION_COOKIE, "")
    _payload, expected_csrf = get_browser_sessions().validate_session(cookie)
    if request.method in UNSAFE_METHODS:
        require_same_origin(request)
        supplied_csrf = request.headers.get("x-hermes-csrf", "")
        if not hmac.compare_digest(supplied_csrf, expected_csrf):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF token rejected",
            )
