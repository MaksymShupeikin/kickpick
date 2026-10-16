"""Create local Compose secret files without printing or overwriting passwords."""
import argparse
import os
from pathlib import Path
import secrets

NAMES = ("postgres_admin_password", "api_db_password", "collector_db_password", "migrator_db_password", "predictor_db_password")


def initialize(directory: Path) -> None:
    if directory.is_symlink():
        raise ValueError("Secret directory must not be a symlink")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory.chmod(0o700)
    for name in NAMES:
        path = directory / name
        if path.exists() or path.is_symlink():
            if path.is_symlink() or not path.is_file() or not path.read_text().strip():
                raise ValueError(f"Invalid existing secret file: {path}")
        else:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(descriptor, "w") as file:
                file.write(secrets.token_hex(32) + "\n")
        # Compose file secrets are bind mounts: mode/uid remapping is not portable.
        # The host directory is private (0700); each service receives only its own files.
        path.chmod(0o444)
    print(f"Secret files ready in {directory}; existing values preserved.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path(__file__).resolve().parents[2] / ".secrets")
    initialize(parser.parse_args().directory)
