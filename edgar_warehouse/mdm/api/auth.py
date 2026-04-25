"""X-API-Key validation against AWS Secrets Manager (or env var fallback)."""
from __future__ import annotations

import json
import os
from typing import Optional

from fastapi import Header, HTTPException, status


_SECRET_CACHE: Optional[set[str]] = None


def _load_keys() -> set[str]:
    """Load valid API keys from AWS Secrets Manager, or fall back to env.

    Caches the result for the lifetime of the process. Restart to rotate.
    """
    global _SECRET_CACHE
    if _SECRET_CACHE is not None:
        return _SECRET_CACHE

    secret_id = os.environ.get("MDM_API_KEY_SECRET_ID")
    if secret_id:
        try:
            import boto3  # type: ignore
        except ImportError:
            boto3 = None  # type: ignore
        if boto3 is not None:
            client = boto3.client("secretsmanager")
            payload = client.get_secret_value(SecretId=secret_id)["SecretString"]
            data = json.loads(payload)
            keys = data.get("keys") if isinstance(data, dict) else None
            if isinstance(keys, list):
                _SECRET_CACHE = set(keys)
                return _SECRET_CACHE

    raw = os.environ.get("MDM_API_KEYS", "")
    _SECRET_CACHE = {k.strip() for k in raw.split(",") if k.strip()}
    return _SECRET_CACHE


def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> str:
    keys = _load_keys()
    if not keys:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API key store not configured",
        )
    if x_api_key is None or x_api_key not in keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid X-API-Key",
        )
    return x_api_key
