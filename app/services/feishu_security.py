import hashlib
import hmac
import json
import time
from base64 import b64decode

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

_TIMESTAMP_MAX_SKEW = 300  # seconds


def verify_signature(
    timestamp: str,
    nonce: str,
    body: bytes,
    signature: str,
    encrypt_key: str,
) -> bool:
    """Verify Feishu v2 webhook signature.

    Feishu signs: sha256(timestamp + nonce + encrypt_key + body)
    and puts the hex digest in X-Lark-Signature.
    """
    try:
        ts = int(timestamp)
    except (ValueError, TypeError):
        return False

    if abs(time.time() - ts) > _TIMESTAMP_MAX_SKEW:
        return False

    msg = (timestamp + nonce + encrypt_key).encode() + body
    expected = hashlib.sha256(msg).hexdigest()
    return hmac.compare_digest(expected, signature)


def decrypt_message(encrypt_str: str, encrypt_key: str) -> dict[str, object]:
    """Decrypt AES-256-CBC encrypted Feishu event payload.

    Feishu uses: key = sha256(encrypt_key)[:32], IV = first 16 bytes of base64-decoded cipher.
    """
    cipher_bytes = b64decode(encrypt_str)
    # First 16 bytes are AES IV
    iv = cipher_bytes[:16]
    ciphertext = cipher_bytes[16:]

    key = hashlib.sha256(encrypt_key.encode()).digest()
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    plaintext = decryptor.update(ciphertext) + decryptor.finalize()

    # Remove PKCS7 padding
    pad_len = plaintext[-1]
    plaintext = plaintext[:-pad_len]

    return json.loads(plaintext.decode("utf-8"))  # type: ignore[no-any-return]


def is_url_verification(payload: dict[str, object]) -> str | None:
    """Return the challenge string if this is a URL verification request, else None."""
    # Schema v2 style: {"type": "url_verification", "challenge": "..."}
    if payload.get("type") == "url_verification":
        return str(payload.get("challenge", ""))
    # Also handle legacy style
    if payload.get("challenge") and not payload.get("header"):
        return str(payload["challenge"])
    return None
