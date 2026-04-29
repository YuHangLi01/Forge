import hashlib
import time

from app.services.feishu_security import (
    decrypt_message,
    is_url_verification,
    verify_signature,
)

_ENCRYPT_KEY = "testsecret123456"


def _make_signature(timestamp: str, nonce: str, body: bytes, key: str) -> str:
    msg = (timestamp + nonce + key).encode() + body
    return hashlib.sha256(msg).hexdigest()


def test_verify_signature_valid() -> None:
    ts = str(int(time.time()))
    nonce = "abc123"
    body = b'{"hello":"world"}'
    sig = _make_signature(ts, nonce, body, _ENCRYPT_KEY)
    assert verify_signature(ts, nonce, body, sig, _ENCRYPT_KEY) is True


def test_verify_signature_tampered_body() -> None:
    ts = str(int(time.time()))
    nonce = "abc123"
    body = b'{"hello":"world"}'
    sig = _make_signature(ts, nonce, body, _ENCRYPT_KEY)
    assert verify_signature(ts, nonce, b'{"tampered":"body"}', sig, _ENCRYPT_KEY) is False


def test_verify_signature_wrong_key() -> None:
    ts = str(int(time.time()))
    nonce = "nonce1"
    body = b"body"
    sig = _make_signature(ts, nonce, body, _ENCRYPT_KEY)
    assert verify_signature(ts, nonce, body, sig, "wrongkey") is False


def test_verify_signature_stale_timestamp() -> None:
    ts = str(int(time.time()) - 400)
    nonce = "n"
    body = b"b"
    sig = _make_signature(ts, nonce, body, _ENCRYPT_KEY)
    assert verify_signature(ts, nonce, body, sig, _ENCRYPT_KEY) is False


def test_verify_signature_invalid_timestamp() -> None:
    assert verify_signature("notanint", "n", b"b", "sig", _ENCRYPT_KEY) is False


def test_is_url_verification_type_field() -> None:
    payload = {"type": "url_verification", "challenge": "test_challenge"}
    assert is_url_verification(payload) == "test_challenge"


def test_is_url_verification_challenge_only() -> None:
    payload = {"challenge": "xyz", "token": "tok"}
    assert is_url_verification(payload) == "xyz"


def test_is_url_verification_not_challenge() -> None:
    payload = {
        "schema": "2.0",
        "header": {"event_type": "im.message.receive_v1"},
        "event": {},
    }
    assert is_url_verification(payload) is None


def test_decrypt_message_roundtrip() -> None:
    """Test AES-256-CBC encrypt → decrypt roundtrip."""
    import base64

    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    key = hashlib.sha256(_ENCRYPT_KEY.encode()).digest()
    iv = b"0123456789abcdef"
    plaintext = b'{"event_type":"test"}'
    # PKCS7 pad to 16-byte boundary
    pad_len = 16 - len(plaintext) % 16
    padded = plaintext + bytes([pad_len] * pad_len)

    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    ciphertext = cipher.encryptor().update(padded) + cipher.encryptor().finalize()

    # Feishu format: IV + ciphertext, then base64
    encrypted = base64.b64encode(iv + ciphertext).decode()
    result = decrypt_message(encrypted, _ENCRYPT_KEY)
    assert result.get("event_type") == "test"
