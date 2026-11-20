"""Crypto core tests (CLAUDE.md §5 acceptance).

round-trip at several sizes; unique DEK + nonce per file; tampered ciphertext
→ InvalidTag; wrong AAD fails; wrapped key ≠ DEK; no plaintext DEK persisted.
"""

from __future__ import annotations

import os

import pytest
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.crypto import integrity
from app.crypto.envelope import EncryptedFile, build_aad, decrypt_file, encrypt_file
from tests.fakes import FakeKeyProvider

FID = "11111111-1111-1111-1111-111111111111"
OWNER = 7


@pytest.fixture
def kp():
    return FakeKeyProvider()


@pytest.mark.parametrize("size", [0, 1, 16, 1024, 1024 * 1024])
def test_round_trip(kp, size):
    plaintext = os.urandom(size)
    enc = encrypt_file(plaintext, file_id=FID, owner_id=OWNER, key_provider=kp)

    assert enc.ciphertext != plaintext  # includes the GCM tag, always differs
    assert enc.wrap_alg == "RSA-OAEP-256"
    assert integrity.verify_sha256(plaintext, enc.sha256)

    out = decrypt_file(
        enc.ciphertext,
        nonce=enc.nonce,
        wrapped_key=enc.wrapped_key,
        kek_key_id=enc.kek_key_id,
        file_id=FID,
        owner_id=OWNER,
        key_provider=kp,
    )
    assert out == plaintext


def test_unique_dek_and_nonce_per_file(kp):
    plaintext = b"identical content"
    a = encrypt_file(plaintext, file_id=FID, owner_id=OWNER, key_provider=kp)
    b = encrypt_file(plaintext, file_id=FID, owner_id=OWNER, key_provider=kp)

    assert a.nonce != b.nonce
    assert a.ciphertext != b.ciphertext
    # Different DEKs -> different wrapped keys.
    assert a.wrapped_key != b.wrapped_key


def test_tampered_ciphertext_raises(kp):
    enc = encrypt_file(b"top secret", file_id=FID, owner_id=OWNER, key_provider=kp)
    tampered = bytearray(enc.ciphertext)
    tampered[0] ^= 0x01
    with pytest.raises(InvalidTag):
        decrypt_file(
            bytes(tampered),
            nonce=enc.nonce,
            wrapped_key=enc.wrapped_key,
            kek_key_id=enc.kek_key_id,
            file_id=FID,
            owner_id=OWNER,
            key_provider=kp,
        )


def test_wrong_aad_owner_fails(kp):
    enc = encrypt_file(b"top secret", file_id=FID, owner_id=OWNER, key_provider=kp)
    with pytest.raises(InvalidTag):
        decrypt_file(
            enc.ciphertext,
            nonce=enc.nonce,
            wrapped_key=enc.wrapped_key,
            kek_key_id=enc.kek_key_id,
            file_id=FID,
            owner_id=OWNER + 1,  # wrong owner -> AAD mismatch
            key_provider=kp,
        )


def test_wrapped_key_is_not_plaintext_dek(kp):
    enc = encrypt_file(b"some payload", file_id=FID, owner_id=OWNER, key_provider=kp)
    dek = kp.unwrap(enc.wrapped_key, enc.kek_key_id)  # recovered for the test only
    assert len(dek) == 32  # 256-bit DEK
    assert enc.wrapped_key != dek
    # The wrapped key cannot be used directly as the AES key.
    with pytest.raises(InvalidTag):
        AESGCM(enc.wrapped_key).decrypt(
            enc.nonce, enc.ciphertext, build_aad(FID, OWNER)
        )


def test_no_plaintext_dek_persisted():
    fields = set(EncryptedFile.__dataclass_fields__.keys())
    assert "dek" not in fields
    assert "key" not in fields
    # The only key material carried is the WRAPPED key.
    assert "wrapped_key" in fields
