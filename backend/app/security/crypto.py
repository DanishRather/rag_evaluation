import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.domain.errors import DomainError


def _key() -> bytes:
    raw = os.environ.get("EVAL_SECRET_KEY", "").strip()
    if not raw:
        raise DomainError("validation_error", "EVAL_SECRET_KEY is required to store a secret")
    return hashlib.sha256(raw.encode()).digest()


def encrypt(value: str) -> tuple[str, str]:
    nonce = os.urandom(12)
    ciphertext = AESGCM(_key()).encrypt(nonce, value.encode(), None)
    return ciphertext.hex(), nonce.hex()


def decrypt(ciphertext: str, nonce: str) -> str:
    try:
        plain = AESGCM(_key()).decrypt(bytes.fromhex(nonce), bytes.fromhex(ciphertext), None)
    except Exception as exc:
        raise DomainError("validation_error", "Secret could not be decrypted") from exc
    return plain.decode()
