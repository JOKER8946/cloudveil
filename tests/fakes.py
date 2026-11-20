"""In-memory fakes for CI — defined only here, never imported by app code.

They implement the KeyProvider / StorageBackend interfaces so the crypto and
files layers can be tested without Azure Key Vault or Blob Storage.
"""

from __future__ import annotations


class FakeKeyProvider:
    """Reversible stand-in for Azure Key Vault wrap/unwrap.

    The 'wrapping' XORs the DEK with a fixed pad so the wrapped bytes clearly
    differ from the plaintext DEK while remaining reversible — enough to test
    the envelope flow without real RSA.
    """

    KEY_ID = "https://fake.vault.azure.net/keys/cloudveil-kek/v1"
    _PAD = 0x5A

    def wrap(self, dek: bytes) -> tuple[bytes, str]:
        return bytes(b ^ self._PAD for b in dek), self.KEY_ID

    def unwrap(self, wrapped_key: bytes, kek_key_id: str) -> bytes:
        return bytes(b ^ self._PAD for b in wrapped_key)


class FakeStorage:
    """In-memory ciphertext store keyed by blob name."""

    def __init__(self):
        self._blobs: dict[str, bytes] = {}
        self._meta: dict[str, dict] = {}

    def put(self, blob_name: str, data: bytes, *, file_id: str) -> None:
        self._blobs[blob_name] = bytes(data)
        self._meta[blob_name] = {"file_id": file_id, "v": "1"}

    def get(self, blob_name: str) -> bytes:
        return self._blobs[blob_name]

    def delete(self, blob_name: str) -> None:
        self._blobs.pop(blob_name, None)
        self._meta.pop(blob_name, None)

    def exists(self, blob_name: str) -> bool:
        return blob_name in self._blobs

    # Test helper (not part of the interface).
    def overwrite_raw(self, blob_name: str, data: bytes) -> None:
        self._blobs[blob_name] = bytes(data)
