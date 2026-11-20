"""Lazily-built, app-scoped crypto key provider and storage backend.

Production builds the Azure implementations from config (managed identity).
Tests inject fakes by setting ``app.config["KEY_PROVIDER"]`` /
``app.config["STORAGE_BACKEND"]``.
"""

from __future__ import annotations

from flask import current_app

from .crypto.keyprovider import AzureKeyVaultProvider, KeyProvider
from .storage.blob import AzureBlobStorage, StorageBackend

_KEY_PROVIDER_ATTR = "_cloudveil_key_provider"
_STORAGE_ATTR = "_cloudveil_storage"


def get_key_provider() -> KeyProvider:
    injected = current_app.config.get("KEY_PROVIDER")
    if injected is not None:
        return injected
    app = current_app._get_current_object()
    provider = getattr(app, _KEY_PROVIDER_ATTR, None)
    if provider is None:
        provider = AzureKeyVaultProvider(
            vault_url=current_app.config["KEYVAULT_URL"],
            key_name=current_app.config.get("KEK_NAME", "cloudveil-kek"),
        )
        setattr(app, _KEY_PROVIDER_ATTR, provider)
    return provider


def get_storage() -> StorageBackend:
    injected = current_app.config.get("STORAGE_BACKEND")
    if injected is not None:
        return injected
    app = current_app._get_current_object()
    storage = getattr(app, _STORAGE_ATTR, None)
    if storage is None:
        storage = AzureBlobStorage(
            account_url=current_app.config["STORAGE_ACCOUNT_URL"],
            container=current_app.config.get("STORAGE_CONTAINER", "encrypted-files"),
        )
        setattr(app, _STORAGE_ATTR, storage)
    return storage
