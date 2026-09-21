"""Consistent SQLite snapshot and its referenced images; excludes credentials and weights."""

import argparse
import io
import sqlite3
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from studio.config import data_dir
from studio.storage.backend import AssetStorage


def backup(root: Path, output: Path, *, storage=None) -> Path:
    storage = storage or AssetStorage(root)
    output.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = output / f"storm-studio-{stamp}.tar.gz"
    temporary = target.with_suffix(".partial")
    try:
        with tempfile.TemporaryDirectory() as scratch:
            snapshot = Path(scratch) / "studio.db"
            source = sqlite3.connect((root / "studio.db").resolve().as_uri() + "?mode=ro", uri=True)
            destination = sqlite3.connect(snapshot)
            try:
                source.backup(destination)
                destination.row_factory = sqlite3.Row
                items = [
                    dict(r) for r in destination.execute("SELECT id, path, sha256 FROM assets")
                ]
                # Portable backup: restored DB points to included local assets, not live OSS.
                for item in items:
                    destination.execute(
                        "UPDATE assets SET path=? WHERE id=?",
                        (f"assets/{item['id']}.png", item["id"]),
                    )
                destination.commit()
                if destination.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("数据库备份校验失败")
            finally:
                destination.close()
                source.close()
            with tarfile.open(temporary, "w:gz") as archive:
                archive.add(snapshot, arcname="studio.db")
                for item in items:
                    # Missing referenced images fail the backup instead of reporting success.
                    content = storage.read_asset(item)
                    info = tarfile.TarInfo(f"assets/{item['id']}.png")
                    info.size, info.mode = len(content), 0o600
                    archive.addfile(info, io.BytesIO(content))
        temporary.replace(target)
        target.chmod(0o600)
        return target
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(backup(data_dir(), args.output).name)
