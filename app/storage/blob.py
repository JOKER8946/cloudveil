"""Storage-backend interface and the Azure Blob Storage implementation.

Only ciphertext is ever written. Blobs are stored at ``files/<blob_name>.bin``
inside the private container, with minimal metadata (``file_id`` and a schema
version) — never the original filename or any key material.

Authenticates with ``DefaultAzureCredential`` (the App Service managed identity
in production); no storage account keys are used. Tests inject
:class:`tests.fakes.FakeStorage`.
"""

from __future__ import annotations

from typing import Protocol

BLOB_PREFIX = "files/"
BLOB_SUFFIX = ".bin"


def blob_path(blob_name: str) -> str:
    return f"{BLOB_PREFIX}{blob_name}{BLOB_SUFFIX}"


class StorageBackend(Protocol):
    """Persist and retrieve ciphertext blobs."""

    def put(self, blob_name: str, data: bytes, *, file_id: str) -> None: ...

    def get(self, blob_name: str) -> bytes: ...

    def delete(self, blob_name: str) -> None: ...

    def exists(self, blob_name: str) -> bool: ...


class AzureBlobStorage:
    """Azure Blob Storage backend for ciphertext (managed identity auth)."""

    def __init__(self, account_url: str, container: str, credential=None):
        self._account_url = account_url
        self._container = container
        self._credential = credential
        self._service = None

    def _service_client(self):
        if self._service is None:
            from azure.identity import DefaultAzureCredential
            from azure.storage.blob import BlobServiceClient

            credential = self._credential or DefaultAzureCredential()
            self._service = BlobServiceClient(
                account_url=self._account_url, credential=credential
            )
        return self._service

    def _blob_client(self, blob_name: str):
        return self._service_client().get_blob_client(
            container=self._container, blob=blob_path(blob_name)
        )

    def put(self, blob_name: str, data: bytes, *, file_id: str) -> None:
        self._blob_client(blob_name).upload_blob(
            data,
            overwrite=True,
            metadata={"file_id": file_id, "v": "1"},
        )

    def get(self, blob_name: str) -> bytes:
        return self._blob_client(blob_name).download_blob().readall()

    def delete(self, blob_name: str) -> None:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            self._blob_client(blob_name).delete_blob()
        except ResourceNotFoundError:
            pass

    def exists(self, blob_name: str) -> bool:
        return self._blob_client(blob_name).exists()
