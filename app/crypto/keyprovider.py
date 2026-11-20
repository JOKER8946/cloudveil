"""Key-provider interface and the Azure Key Vault implementation.

A ``KeyProvider`` wraps and unwraps the per-file data key (DEK) using a master
key (KEK) that never leaves its backing store. The production implementation
uses an RSA key in Azure Key Vault via ``CryptographyClient`` (RSA-OAEP-256).
The KEK private key material never leaves Key Vault — only wrap/unwrap
operations cross the boundary.

Tests inject :class:`tests.fakes.FakeKeyProvider` instead.
"""

from __future__ import annotations

from typing import Protocol

WRAP_ALG = "RSA-OAEP-256"


class KeyProvider(Protocol):
    """Wrap/unwrap a data key with a managed master key."""

    def wrap(self, dek: bytes) -> tuple[bytes, str]:
        """Return (wrapped_key, kek_key_id) for the given plaintext DEK."""
        ...

    def unwrap(self, wrapped_key: bytes, kek_key_id: str) -> bytes:
        """Return the plaintext DEK for a wrapped key + the KEK id used."""
        ...


class AzureKeyVaultProvider:
    """Wrap/unwrap DEKs with an RSA key in Azure Key Vault (RSA-OAEP-256).

    Authenticates with ``DefaultAzureCredential`` (the App Service managed
    identity in production). A ``CryptographyClient`` is cached per KEK key id.
    """

    def __init__(self, vault_url: str, key_name: str, credential=None):
        self._vault_url = vault_url
        self._key_name = key_name
        self._credential = credential
        self._key_client = None
        self._crypto_clients: dict[str, object] = {}

    def _credential_or_default(self):
        if self._credential is not None:
            return self._credential
        from azure.identity import DefaultAzureCredential

        self._credential = DefaultAzureCredential()
        return self._credential

    def _get_key_client(self):
        if self._key_client is None:
            from azure.keyvault.keys import KeyClient

            self._key_client = KeyClient(
                vault_url=self._vault_url, credential=self._credential_or_default()
            )
        return self._key_client

    def _crypto_client_for(self, key_id: str):
        client = self._crypto_clients.get(key_id)
        if client is None:
            from azure.keyvault.keys.crypto import CryptographyClient

            client = CryptographyClient(
                key_id, credential=self._credential_or_default()
            )
            self._crypto_clients[key_id] = client
        return client

    def _current_key_id(self) -> str:
        """Resolve the latest version id of the configured KEK."""
        key = self._get_key_client().get_key(self._key_name)
        return key.id

    def wrap(self, dek: bytes) -> tuple[bytes, str]:
        from azure.keyvault.keys.crypto import KeyWrapAlgorithm

        key_id = self._current_key_id()
        result = self._crypto_client_for(key_id).wrap_key(
            KeyWrapAlgorithm.rsa_oaep_256, dek
        )
        # result.key_id carries the exact key version used.
        return result.encrypted_key, result.key_id

    def unwrap(self, wrapped_key: bytes, kek_key_id: str) -> bytes:
        from azure.keyvault.keys.crypto import KeyWrapAlgorithm

        result = self._crypto_client_for(kek_key_id).unwrap_key(
            KeyWrapAlgorithm.rsa_oaep_256, wrapped_key
        )
        return result.key
