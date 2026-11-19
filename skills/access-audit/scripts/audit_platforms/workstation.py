"""The operator's workstation: client credential files, read directly (counts only, never a value)."""
from __future__ import annotations

import re
import stat
from pathlib import Path

from .base import control

NAME = "workstation"
FILES = [Path(".snowflake/connections.toml"), Path(".aws/credentials"), Path(".config/edgartools/edgar.env"), Path(".config/edgartools/openfigi.env")]
FOLDERS = [Path(".snowflake/keys"), Path(".config/edgartools/hosted")]


def configured(env) -> bool:
    return True


def collect(env, as_admin: bool = False) -> dict:
    home = Path(env.get("AUDIT_HOME") or Path.home())
    plain, loose, held = 0, [], 0
    for rel in FILES:
        path = home / rel
        if path.exists():
            held += 1
            plain += len(re.findall(r"^\s*(password|aws_secret_access_key)\s*=", path.read_text(errors="replace"), re.M | re.I))
            if stat.S_IMODE(path.stat().st_mode) & 0o077:
                loose.append(rel.name)
    for folder in FOLDERS:
        for path in (home / folder).glob("*") if (home / folder).exists() else []:
            if path.is_file() and path.suffix != ".pub":
                held += 1
                if stat.S_IMODE(path.stat().st_mode) & 0o077:
                    loose.append(path.name)
    return {"plaintext_passwords": plain, "loose_files": loose, "files_held": held}


def principals(ev: dict) -> list[str]:
    return []


def controls(ev: dict) -> list[dict]:
    return [control(NAME, "SEC", ev["plaintext_passwords"] == 0 and not ev["loose_files"],
                    {"credential_files_read": ev["files_held"], "plaintext_passwords": ev["plaintext_passwords"], "files_readable_by_others": len(ev["loose_files"])},
                    "Key pair, role or keychain instead of a password in a file; chmod 600")]
