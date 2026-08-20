"""Local secrets vault: simple encrypted folder per-vault using a password.

This is intentionally local-only: keys and secrets never leave the user's
machine. The vault metadata stores a salt for PBKDF2 so the password derives
to a symmetric key used by Fernet (cryptography).

APIs:
- init_vault(path, password)
- open_vault(path, password) -> Vault

Vault methods:
- add(name, data)
- get(name) -> bytes
- list() -> list[str]
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
import base64
from typing import Optional

from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
from cryptography.fernet import Fernet


def _derive_key(password: str, salt: bytes, iterations: int = 390000) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=iterations,
        backend=default_backend(),
    )
    key = kdf.derive(password.encode())
    return base64.urlsafe_b64encode(key)


@dataclass
class Vault:
    path: Path
    key: bytes

    @property
    def data_dir(self) -> Path:
        return self.path / "data"

    def _ensure(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def add(self, name: str, data: bytes) -> None:
        self._ensure()
        f = Fernet(self.key)
        token = f.encrypt(data)
        (self.data_dir / f"{name}.enc").write_bytes(token)
        try:
            from buster.secrets.audit import log_event

            log_event("vault.add", str(self.path), name, True)
        except Exception:
            pass

    def get(self, name: str) -> Optional[bytes]:
        p = self.data_dir / f"{name}.enc"
        if not p.exists():
            try:
                from buster.secrets.audit import log_event

                log_event("vault.get", str(self.path), name, False, note="not_found")
            except Exception:
                pass
            return None
        token = p.read_bytes()
        f = Fernet(self.key)
        try:
            out = f.decrypt(token)
            try:
                from buster.secrets.audit import log_event

                log_event("vault.get", str(self.path), name, True)
            except Exception:
                pass
            return out
        except Exception:
            try:
                from buster.secrets.audit import log_event

                log_event("vault.get", str(self.path), name, False, note="decrypt_failed")
            except Exception:
                pass
            raise

    def list(self) -> list[str]:
        if not self.data_dir.exists():
            return []
        return [p.stem.replace('.enc','') if p.suffix=='.enc' else p.stem for p in self.data_dir.iterdir() if p.is_file()]


def init_vault(path: Path, password: str) -> Vault:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    meta = path / "vault.meta.json"
    if meta.exists():
        raise FileExistsError("Vault already exists")
    salt = os.urandom(16)
    iterations = 390000
    meta.write_text(json.dumps({"salt": base64.b64encode(salt).decode(), "iterations": iterations}))
    key = _derive_key(password, salt, iterations)
    # Audit: vault created
    try:
        from buster.secrets.audit import log_event

        log_event("vault.init", str(path), None, True)
    except Exception:
        pass
    return Vault(path=path, key=key)


def open_vault(path: Path, password: str) -> Vault:
    path = Path(path)
    meta = path / "vault.meta.json"
    if not meta.exists():
        raise FileNotFoundError("No vault at path")
    raw = json.loads(meta.read_text())
    salt = base64.b64decode(raw["salt"])
    iterations = int(raw.get("iterations", 390000))
    key = _derive_key(password, salt, iterations)
    # Validate by attempting to open data dir (no items means OK). If decryption
    # of existing items fails, user will see errors when calling get().
    try:
        from buster.secrets.audit import log_event

        log_event("vault.open", str(path), None, True)
    except Exception:
        pass
    return Vault(path=path, key=key)
