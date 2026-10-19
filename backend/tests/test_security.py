import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app import security


def setup_module():
    # No network, database, or real signing credentials needed for these tests.
    security.get_settings = lambda: SimpleNamespace(jwt_secret="a" * 64)


def test_argon2_round_trip():
    hashed = security.hash_password("secure-password-12345")
    assert hashed != "secure-password-12345"
    assert security.verify_password(hashed, "secure-password-12345")
    assert not security.verify_password(hashed, "incorrect")


def test_session_and_csrf_require_same_signed_identity():
    token = security.new_session_token(uuid.uuid4())
    claims = security.decode_session(token)
    expected = security.csrf_token(claims)
    security.check_csrf(claims, expected)
    with pytest.raises(HTTPException) as err:
        security.check_csrf(claims, "invalid")
    assert err.value.status_code == 403
    with pytest.raises(HTTPException) as err:
        security.decode_session(token + "tampered")
    assert err.value.status_code == 401


def test_invite_tokens_are_random_and_not_stored_plaintext():
    one, digest1 = security.make_invite_token()
    two, digest2 = security.make_invite_token()
    assert one != two and digest1 != digest2
    assert one != digest1
    assert security.invite_digest(one) == digest1
