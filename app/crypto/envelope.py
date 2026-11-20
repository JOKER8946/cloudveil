"""Envelope encryption: per-file AES-256-GCM data key, wrapped by the KEK.

Flow (see CLAUDE.md §5):
  * encrypt: generate a random 256-bit DEK and 96-bit nonce, AES-GCM encrypt the
    plaintext with an AAD binding the ciphertext to (file_id, owner_id), then
    wrap the DEK with the KEK. Only the *wrapped* DEK is ever persisted.
  * decrypt: unwrap the DEK, AES-GCM decrypt (authenticating the AAD). A tampered
    ciphertext, nonce, or mismatched AAD raises ``cryptography``'s ``InvalidTag``.

The plaintext DEK exists only transiently in memory and is never returned to or
stored by callers.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .keyprovider import WRAP_ALG, KeyProvider

DEK_BITS = 256
NONCE_BYTES = 12
AAD_VERSION = "v1"


@dataclass(frozen=True)
class EncryptedFile:
    """Result of encrypting one file. Contains no plaintext key material."""

    ciphertext: bytes
    nonce: bytes
    wrapped_key: bytes
    kek_key_id: str
    wrap_alg: str
    sha256: str


def build_aad(file_id: str, owner_id: int) -> bytes:
    """Additional authenticated data binding ciphertext to file + owner."""
    return f"cloudveil:{AAD_VERSION}:{file_id}:{owner_id}".encode()


def encrypt_file(
    plaintext: bytes,
    *,
    file_id: str,
    owner_id: int,
    key_provider: KeyProvider,
) -> EncryptedFile:
    """Encrypt ``plaintext`` and wrap its data key."""
    dek = AESGCM.generate_key(bit_length=DEK_BITS)
    nonce = os.urandom(NONCE_BYTES)
    sha256 = hashlib.sha256(plaintext).hexdigest()
    aad = build_aad(file_id, owner_id)

    ciphertext = AESGCM(dek).encrypt(nonce, plaintext, aad)
    wrapped_key, kek_key_id = key_provider.wrap(dek)

    # Drop the plaintext DEK reference; GC reclaims it.
    del dek
    return EncryptedFile(
        ciphertext=ciphertext,
        nonce=nonce,
        wrapped_key=wrapped_key,
        kek_key_id=kek_key_id,
        wrap_alg=WRAP_ALG,
        sha256=sha256,
    )


def decrypt_file(
    ciphertext: bytes,
    *,
    nonce: bytes,
    wrapped_key: bytes,
    kek_key_id: str,
    file_id: str,
    owner_id: int,
    key_provider: KeyProvider,
) -> bytes:
    """Unwrap the DEK and AES-GCM decrypt.

    Raises ``cryptography.exceptions.InvalidTag`` if the ciphertext, nonce or
    AAD do not authenticate (tampering / wrong file binding).
    """
    dek = key_provider.unwrap(wrapped_key, kek_key_id)
    aad = build_aad(file_id, owner_id)
    try:
        return AESGCM(dek).decrypt(nonce, ciphertext, aad)
    finally:
        del dek
