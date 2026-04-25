"""Typed storage adapter with path-safety guards."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse

from edgar_warehouse.application.errors import WarehouseRuntimeError

ALLOWED_REMOTE_PROTOCOLS = frozenset({"abfs", "abfss", "az", "s3"})
_AZURE_HTTPS_SUFFIXES = (
    ".blob.core.windows.net",
    ".dfs.core.windows.net",
)


def sanitize_relative_path(relative_path: str) -> str:
    candidate = str(relative_path or "").strip().replace("\\", "/")
    if not candidate:
        raise WarehouseRuntimeError("relative storage path must not be empty")
    path = PurePosixPath(candidate)
    if path.is_absolute():
        raise WarehouseRuntimeError(f"absolute storage paths are not allowed: {relative_path}")
    cleaned_parts: list[str] = []
    for part in path.parts:
        if part in {"", "."}:
            continue
        if part == "..":
            raise WarehouseRuntimeError(f"path traversal is not allowed: {relative_path}")
        cleaned_parts.append(part)
    if not cleaned_parts:
        raise WarehouseRuntimeError("relative storage path must not resolve to empty")
    return "/".join(cleaned_parts)


def sanitize_filename(filename: str) -> str:
    candidate = str(filename or "").strip().replace("\\", "/")
    if not candidate:
        raise WarehouseRuntimeError("document name must not be empty")
    name = PurePosixPath(candidate).name
    if name in {"", ".", ".."}:
        raise WarehouseRuntimeError(f"invalid document name: {filename}")
    return name


def _protocol_for_uri(uri: str) -> str | None:
    if "://" not in uri:
        return None
    return uri.split("://", 1)[0].lower()


def _is_azure_https_url(uri: str) -> bool:
    if _protocol_for_uri(uri) != "https":
        return False
    try:
        host = (urlparse(uri).hostname or "").lower()
    except ValueError:
        return False
    return host.endswith(_AZURE_HTTPS_SUFFIXES)


def _normalize_azure_https_url(uri: str) -> str:
    parsed = urlparse(uri)
    host = (parsed.hostname or "").lower()
    account = host.split(".", 1)[0]
    path_parts = [part for part in parsed.path.split("/") if part]
    if not account or not path_parts:
        raise WarehouseRuntimeError(f"invalid Azure storage URL: {uri}")
    container = path_parts[0]
    relative_path = "/".join(path_parts[1:])
    root = f"abfss://{container}@{account}.dfs.core.windows.net"
    if relative_path:
        return f"{root}/{relative_path}"
    return root


def _assert_protocol_allowed(protocol: str | None) -> None:
    if protocol is None:
        return
    if protocol not in ALLOWED_REMOTE_PROTOCOLS:
        raise WarehouseRuntimeError(f"unsupported storage protocol: {protocol}")


def _azure_account_name_from_uri(uri: str) -> str | None:
    parsed = urlparse(uri)
    host = (parsed.hostname or "").lower()
    if not host:
        return None
    if "." in host:
        return host.split(".", 1)[0]
    return host


def _default_azure_credential() -> Any:
    try:
        from azure.identity import DefaultAzureCredential
    except ImportError as exc:
        raise WarehouseRuntimeError(
            "Azure storage roots require the 'azure' optional dependency group"
        ) from exc
    return DefaultAzureCredential()


def _remote_storage_options(storage_path: str) -> dict[str, Any]:
    protocol = _protocol_for_uri(storage_path)
    if protocol not in {"abfs", "abfss", "az"}:
        return {}

    account_name = _azure_account_name_from_uri(storage_path) or os.getenv("AZURE_STORAGE_ACCOUNT")
    if not account_name:
        raise WarehouseRuntimeError(f"Azure storage account name could not be resolved from: {storage_path}")
    return {
        "account_name": account_name,
        "credential": _default_azure_credential(),
    }


@dataclass(frozen=True)
class StorageLocation:
    """A storage root that can point to a local path or approved cloud URI."""

    root: str

    def __post_init__(self) -> None:
        normalized = str(self.root or "").strip()
        if not normalized:
            raise WarehouseRuntimeError("storage root must not be empty")
        protocol = _protocol_for_uri(normalized)
        if protocol == "https" and _is_azure_https_url(normalized):
            normalized = _normalize_azure_https_url(normalized)
            protocol = _protocol_for_uri(normalized)
            _assert_protocol_allowed(protocol)
            object.__setattr__(self, "root", normalized.rstrip("/\\"))
            return
        _assert_protocol_allowed(protocol)
        object.__setattr__(self, "root", normalized.rstrip("/\\"))

    @property
    def is_remote(self) -> bool:
        return "://" in self.root

    def join(self, *parts: str) -> str:
        relative = sanitize_relative_path("/".join(str(part or "").strip("/\\") for part in parts if part))
        if self.is_remote:
            return f"{self.root}/{relative}"
        return str(Path(self.root).joinpath(*PurePosixPath(relative).parts))

    def write_json(self, relative_path: str, payload: dict[str, Any]) -> str:
        return self.write_text(relative_path, json.dumps(payload, indent=2, sort_keys=True) + "\n")

    def write_text(self, relative_path: str, payload: str) -> str:
        return self.write_bytes(relative_path, payload.encode("utf-8"))

    def write_bytes(self, relative_path: str, payload: bytes) -> str:
        relative = sanitize_relative_path(relative_path)
        destination = self.join(relative)
        if self.is_remote:
            protocol = _protocol_for_uri(self.root)
            _assert_protocol_allowed(protocol)
            import fsspec

            fs = fsspec.filesystem(protocol, **_remote_storage_options(destination))
            with fs.open(destination, "wb") as handle:
                handle.write(payload)
            return destination

        destination_path = Path(destination)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        destination_path.write_bytes(payload)
        return str(destination_path)


def read_bytes(storage_path: str) -> bytes:
    protocol = _protocol_for_uri(storage_path)
    if protocol is None:
        return Path(storage_path).read_bytes()
    if protocol == "https" and _is_azure_https_url(storage_path):
        storage_path = _normalize_azure_https_url(storage_path)
        protocol = _protocol_for_uri(storage_path)
    _assert_protocol_allowed(protocol)
    import fsspec

    fs = fsspec.filesystem(protocol, **_remote_storage_options(storage_path))
    with fs.open(storage_path, "rb") as handle:
        return handle.read()
