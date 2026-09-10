"""密码哈希与轻量 JWT（仅依赖标准库，SDD 9.2）。

生产环境可替换为 passlib+bcrypt / python-jose，接口保持不变。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time


def hash_password(password: str, *, iterations: int = 120_000) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt_hex, hash_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(),
                                 bytes.fromhex(salt_hex), int(iterations))
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception:  # noqa: BLE001
        return False


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def create_access_token(secret: bytes, payload: dict, ttl_hours: int = 12) -> str:
    body = {**payload, "exp": int(time.time()) + ttl_hours * 3600}
    header = _b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    body_s = _b64encode(json.dumps(body, separators=(",", ":")).encode())
    sig = hmac.new(secret, f"{header}.{body_s}".encode(), hashlib.sha256).digest()
    return f"{header}.{body_s}.{_b64encode(sig)}"


def decode_token(secret: bytes, token: str) -> dict:
    try:
        header_s, body_s, sig_s = token.split(".")
        expected = _b64encode(
            hmac.new(secret, f"{header_s}.{body_s}".encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(expected, sig_s):
            raise ValueError("签名错误")
        payload = json.loads(_b64decode(body_s))
        if payload.get("exp", 0) < time.time():
            raise ValueError("token 已过期")
        return payload
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ValueError("非法 token") from exc
