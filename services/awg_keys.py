"""WireGuard/AmneziaWG keypair generation (pure Python, no `awg` binary).

WireGuard keys are Curve25519 (X25519): a 32-byte private scalar and its
derived 32-byte public point, each base64-encoded. AmneziaWG uses the same key
format — the obfuscation lives in the transport, not the keys.
"""
from __future__ import annotations

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def generate_keypair() -> tuple[str, str]:
    """Return (private_key_b64, public_key_b64) in WireGuard format."""
    private = X25519PrivateKey.generate()
    private_raw = private.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_raw = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return _b64(private_raw), _b64(public_raw)


def public_key_for(private_key_b64: str) -> str:
    """Derive the base64 public key from a base64 private key."""
    private = X25519PrivateKey.from_private_bytes(base64.b64decode(private_key_b64))
    public_raw = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return _b64(public_raw)
