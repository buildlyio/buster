import tempfile
import os
from pathlib import Path

from buster.secrets.manager import init_vault, open_vault


def run_demo():
    td = Path(tempfile.mkdtemp(prefix="buster_vault_"))
    vault_dir = td / "vault"
    pwd = "demo-password"
    print("Initializing vault at", vault_dir)
    v = init_vault(vault_dir, pwd)
    v.add("api_key", b"secret-key-123")
    print("Stored 'api_key'. Listing entries:", v.list())
    v2 = open_vault(vault_dir, pwd)
    print("Retrieved api_key:", v2.get("api_key"))


if __name__ == '__main__':
    run_demo()
