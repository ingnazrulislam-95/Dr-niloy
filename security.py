"""Password hashing and signed session tokens (standard library only)."""
import hashlib
import hmac
import os
import time


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_hex, digest_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1, dklen=32
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except Exception:
        return False


def make_token(user_id: int, secret: bytes, ttl: int = 8 * 3600) -> str:
    payload = f"{user_id}.{int(time.time()) + ttl}"
    sig = hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def read_token(token: str | None, secret: bytes) -> int | None:
    if not token:
        return None
    try:
        user_id, expires, sig = token.split(".")
        expected = hmac.new(secret, f"{user_id}.{expires}".encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected) or int(expires) < time.time():
            return None
        return int(user_id)
    except Exception:
        return None
