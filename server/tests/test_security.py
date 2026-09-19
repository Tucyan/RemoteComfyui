from __future__ import annotations

import time

import pytest

from app.security import PairingService, TokenService


def test_pairing_code_is_one_time_and_expiring(tmp_path):
    service = PairingService(tmp_path / "gateway.db", pairing_ttl=30)
    code = service.create_pairing_code(now=100)

    token = service.redeem_pairing_code(code, "Pixel 9", now=101)
    assert token.startswith("rc_")
    assert service.authenticate(token)["name"] == "Pixel 9"

    with pytest.raises(ValueError, match="invalid or expired"):
        service.redeem_pairing_code(code, "second", now=102)

    expired = service.create_pairing_code(now=200)
    with pytest.raises(ValueError, match="invalid or expired"):
        service.redeem_pairing_code(expired, "late", now=231)


def test_device_tokens_are_hashed_and_revocable(tmp_path):
    service = PairingService(tmp_path / "gateway.db")
    code = service.create_pairing_code()
    raw_token = service.redeem_pairing_code(code, "Android")

    rows = service.list_devices()
    assert len(rows) == 1
    assert raw_token not in rows[0].values()
    assert len(rows[0]["token_hash"]) == 64

    assert service.authenticate(raw_token)["id"] == rows[0]["id"]
    service.revoke_device(rows[0]["id"])
    with pytest.raises(PermissionError):
        service.authenticate(raw_token)


def test_token_service_uses_constant_time_hash_lookup(tmp_path):
    service = TokenService(tmp_path / "tokens.db")
    raw = service.issue("test-device")
    assert service.verify(raw)["device_name"] == "test-device"
    with pytest.raises(PermissionError):
        service.verify("rc_invalid")
