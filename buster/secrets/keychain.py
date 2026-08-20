"""OS keychain integration (optional via `keyring`).

Provides simple helpers to store/retrieve vault passwords in the user's
OS credential store (macOS Keychain, Windows Credential Manager, or a
platform-appropriate backend provided by the `keyring` package).
"""
from __future__ import annotations

from typing import Optional

try:
    import keyring
except Exception:  # pragma: no cover - optional dependency
    keyring = None


SERVICE_PREFIX = "buster.setec-astronomy"


def available() -> bool:
    return keyring is not None


def set_vault_password(vault_name: str, password: str) -> bool:
    if not keyring:
        return False
    service = f"{SERVICE_PREFIX}.{vault_name}"
    keyring.set_password(service, "vault_password", password)
    return True


def get_vault_password(vault_name: str) -> Optional[str]:
    if not keyring:
        return None
    service = f"{SERVICE_PREFIX}.{vault_name}"
    return keyring.get_password(service, "vault_password")
