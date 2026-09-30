"""Consistent SQLite snapshot and its referenced images; excludes credentials and weights."""

import argparse
import io
import sqlite3
import tarfile
import tempfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from studio.config import data_dir
from studio.storage.backend import AssetStorage


def snapshot_db(source_path, target):
    source = sqlite3.connect(source_path.resolve().as_uri() + "?mode=ro", uri=True)
    destination = sqlite3.connect(target)
    try:
        source.backup(destination)
        if destination.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("数据库备份校验失败")
    finally:
        destination.close()
        source.close()
    target.chmod(0o600)


def backup(root: Path, output: Path, *, storage=None) -> Path:
    storage = storage or AssetStorage(root)
    output.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = output / f"storm-studio-{stamp}.tar.gz"
    temporary = target.with_suffix(".partial")
    try:
        with tempfile.TemporaryDirectory() as scratch, tarfile.open(temporary, "w:gz") as archive:
            roots = [(root, "", storage)]
            if (root / "accounts.db").exists():
                snapshot = Path(scratch) / "accounts.db"
                snapshot_db(root / "accounts.db", snapshot)
                with closing(sqlite3.connect(snapshot)) as db, db:
                    # Password hashes must survive disaster recovery; live sessions must not.
                    db.execute("DELETE FROM sessions")
                    db.execute("DELETE FROM attempts")
                    for (user_id,) in db.execute("SELECT id FROM users WHERE owner=0"):
                        import re

                        if not re.fullmatch(r"[a-f0-9]{32}", user_id):
                            raise ValueError("无效的账号目录")
                        tenant = root / "users" / user_id
                        if not (tenant / "studio.db").exists():
                            from studio.repositories.db import engine_for, metadata

                            engine = engine_for(Path(scratch) / user_id)
                            metadata.create_all(engine)
                            engine.dispose()
                            tenant = Path(scratch) / user_id
                        roots.append(
                            (tenant, f"users/{user_id}/", AssetStorage(tenant, storage.settings))
                        )
                archive.add(snapshot, arcname="accounts.db")
            for index, (tenant, prefix, tenant_storage) in enumerate(roots):
                snapshot = Path(scratch) / f"workflow-{index}.db"
                snapshot_db(tenant / "studio.db", snapshot)
                with closing(sqlite3.connect(snapshot)) as db, db:
                    db.row_factory = sqlite3.Row
                    items = [dict(r) for r in db.execute("SELECT id,path,sha256 FROM assets")]
                    for item in items:
                        db.execute(
                            "UPDATE assets SET path=? WHERE id=?",
                            (f"assets/{item['id']}.png", item["id"]),
                        )
                archive.add(snapshot, arcname=prefix + "studio.db")
                for item in items:
                    content = tenant_storage.read_asset(item)
                    info = tarfile.TarInfo(prefix + f"assets/{item['id']}.png")
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
