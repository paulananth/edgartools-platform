"""Bootstrap the local OpenMetadata account and keep its PAT in a private .env."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import secrets
import string
import sys
import tempfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

DEFAULT_URL = "http://127.0.0.1:8587"
DEFAULT_EMAIL = "admin@open-metadata.org"
TOKEN_NAME = "edgartools-local-catalog"
PINNED_VERSION = "2.0.7"


class CredentialError(RuntimeError):
    """Safe operator-facing failure that never includes a secret or response body."""


def secure_password() -> str:
    alphabet = string.ascii_letters + string.digits
    required = [
        secrets.choice(group)
        for group in (string.ascii_lowercase, string.ascii_uppercase, string.digits)
    ]
    # OpenMetadata 2.0.7 requires all three character classes and a special
    # character, and limits passwords to 56 characters. ``@`` is both allowed
    # by its validator and safe in an unquoted shell assignment.
    required.append("@")
    required.extend(secrets.choice(alphabet) for _ in range(52))
    secrets.SystemRandom().shuffle(required)
    return "".join(required)


def write_env(path: Path, updates: dict[str, str | None]) -> None:
    """Atomically write the small set of OpenMetadata keys, preserving other entries."""
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = existing.splitlines()
    for key, value in updates.items():
        pattern = re.compile(rf"^{re.escape(key)}=")
        matches = [index for index, line in enumerate(lines) if pattern.match(line)]
        if value is None:
            for index in reversed(matches):
                del lines[index]
            continue
        if not re.fullmatch(r"[A-Za-z0-9@._:/+-]+", value):
            raise CredentialError(
                "Generated credential cannot be stored as a shell-safe .env value"
            )
        replacement = f"{key}={value}"
        if matches:
            lines[matches[0]] = replacement
            for index in reversed(matches[1:]):
                del lines[index]
        else:
            lines.append(replacement)
    content = "\n".join(lines).rstrip("\n") + "\n"
    fd, temporary = tempfile.mkstemp(
        prefix=".openmetadata-env-", dir=path.parent, text=True
    )
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    env_file = args.env_file.expanduser().resolve()
    endpoint = (
        os.environ.get("OPENMETADATA_URL", DEFAULT_URL)
        .rstrip("/")
        .removesuffix("/api/v1")
    )
    try:
        parsed = urlsplit(endpoint)
    except ValueError:
        raise CredentialError("Set a valid local OPENMETADATA_URL") from None
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost"}
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise CredentialError(
            "Credential bootstrap is restricted to a local HTTP OpenMetadata endpoint"
        )

    def call(
        method: str, path: str, body: dict | None = None, token: str = ""
    ) -> dict | None:
        request = Request(
            endpoint + "/api/v1" + path,
            method=method,
            data=None if body is None else json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                **({"Authorization": "Bearer " + token} if token else {}),
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                payload = response.read()
        except HTTPError as error:
            raise CredentialError(
                f"OpenMetadata {method} failed (HTTP {error.code}); check the local service and credentials"
            ) from None
        except (URLError, TimeoutError, OSError):
            raise CredentialError(
                "OpenMetadata did not answer; check local service health"
            ) from None
        try:
            result = json.loads(payload) if payload else None
        except (ValueError, UnicodeDecodeError):
            # Password changes may return a successful plain-text message. The
            # callers that need structured data validate their required fields.
            return None
        return result if isinstance(result, dict) else None

    def login(email: str, password: str) -> str:
        response = call(
            "POST",
            "/users/login",
            {
                "email": email,
                "password": base64.b64encode(password.encode("utf-8")).decode("ascii"),
            },
        )
        token = response.get("accessToken") if response else None
        if not isinstance(token, str) or not token:
            raise CredentialError(
                "OpenMetadata login response did not contain an access token"
            )
        return token

    try:
        email = os.environ.get("OPENMETADATA_LOGIN_EMAIL", DEFAULT_EMAIL)
        configured_password = os.environ.get("OPENMETADATA_LOGIN_PASSWORD", "")
        password_changed = (
            os.environ.get("OPENMETADATA_PASSWORD_CHANGED", "false").lower() == "true"
        )
        initial_password = os.environ.get("OPENMETADATA_INITIAL_PASSWORD", "")
        token = os.environ.get("OPENMETADATA_TOKEN", "")
        if (token or password_changed) and not configured_password:
            raise CredentialError(
                "OPENMETADATA_LOGIN_PASSWORD is missing from the private environment file"
            )
        password = configured_password or secure_password()

        write_env(
            env_file,
            {
                "OPENMETADATA_URL": endpoint,
                "OPENMETADATA_LOGIN_EMAIL": email,
                "OPENMETADATA_LOGIN_PASSWORD": password,
                "OPENMETADATA_PASSWORD_CHANGED": str(password_changed).lower(),
            },
        )

        # A healthy existing PAT is retained. It is never printed or returned to shell output.
        if token:
            try:
                version = call("GET", "/system/version", token=token)
                if version and version.get("version") == PINNED_VERSION:
                    print(
                        json.dumps(
                            {
                                "stage": "credentials",
                                "status": "confirmed",
                                "version": PINNED_VERSION,
                                "login_saved": True,
                                "personal_access_token_saved": True,
                            },
                            sort_keys=True,
                        )
                    )
                    return 0
            except CredentialError:
                pass

        if not password_changed:
            try:
                access_token = login(email, password)
            except CredentialError:
                if not initial_password:
                    raise CredentialError(
                        "OPENMETADATA_INITIAL_PASSWORD is missing from the private environment file"
                    ) from None
                bootstrap_token = login(email, initial_password)
                call(
                    "PUT",
                    "/users/changePassword",
                    {
                        "oldPassword": initial_password,
                        "newPassword": password,
                        "confirmPassword": password,
                        "requestType": "SELF",
                    },
                    token=bootstrap_token,
                )
                access_token = login(email, password)
            password_changed = True
            write_env(
                env_file,
                {
                    "OPENMETADATA_PASSWORD_CHANGED": "true",
                    "OPENMETADATA_INITIAL_PASSWORD": None,
                },
            )

        else:
            access_token = login(email, password)
        version = call("GET", "/system/version", token=access_token)
        if not version or version.get("version") != PINNED_VERSION:
            raise CredentialError(
                "Credential bootstrap requires the pinned OpenMetadata 2.0.7 server"
            )

        personal_token = call(
            "PUT",
            "/users/security/token",
            {
                "tokenName": TOKEN_NAME,
                "JWTTokenExpiry": "30",
            },
            token=access_token,
        )
        jwt_token = personal_token.get("jwtToken") if personal_token else None
        if not isinstance(jwt_token, str) or not jwt_token:
            raise CredentialError("OpenMetadata did not return a personal access token")
        confirmed = call("GET", "/system/version", token=jwt_token)
        if not confirmed or confirmed.get("version") != PINNED_VERSION:
            raise CredentialError(
                "The new personal access token did not pass the API readback"
            )
        write_env(
            env_file,
            {
                "OPENMETADATA_URL": endpoint,
                "OPENMETADATA_LOGIN_EMAIL": email,
                "OPENMETADATA_LOGIN_PASSWORD": password,
                "OPENMETADATA_PASSWORD_CHANGED": "true",
                "OPENMETADATA_TOKEN": jwt_token,
            },
        )
    except CredentialError as error:
        print(
            json.dumps(
                {"stage": "credentials", "status": "failed", "cause": str(error)}
            ),
            file=sys.stderr,
        )
        return 1

    print(
        json.dumps(
            {
                "stage": "credentials",
                "status": "confirmed",
                "version": PINNED_VERSION,
                "login_saved": True,
                "personal_access_token_saved": True,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
