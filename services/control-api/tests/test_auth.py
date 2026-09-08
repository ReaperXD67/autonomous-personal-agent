from __future__ import annotations

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.auth import BrowserSessionManager, require_same_origin


def test_browser_bootstrap_is_one_use_and_session_is_signed() -> None:
    manager = BrowserSessionManager("x" * 32, 3600)
    code = manager.issue_bootstrap()

    session = manager.consume_bootstrap(code)
    _payload, csrf_token = manager.validate_session(session.cookie)

    assert csrf_token == session.csrf_token
    assert session.max_age == 3600
    with pytest.raises(HTTPException, match="invalid or expired"):
        manager.consume_bootstrap(code)


def test_browser_session_rejects_tampering() -> None:
    manager = BrowserSessionManager("x" * 32, 3600)
    session = manager.consume_bootstrap(manager.issue_bootstrap())

    with pytest.raises(HTTPException, match="Browser session required"):
        manager.validate_session(session.cookie + "tampered")


def _request(origin: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "path": "/v1/auth/browser-session",
            "raw_path": b"/v1/auth/browser-session",
            "query_string": b"",
            "headers": [
                (b"host", b"127.0.0.1:8080"),
                (b"origin", origin.encode("ascii")),
            ],
            "server": ("127.0.0.1", 8080),
            "client": ("127.0.0.1", 50000),
        }
    )


def test_same_origin_rejects_cross_origin_bootstrap_exchange() -> None:
    require_same_origin(_request("http://127.0.0.1:8080"))

    with pytest.raises(HTTPException, match="Origin rejected"):
        require_same_origin(_request("http://attacker.invalid"))
