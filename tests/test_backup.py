import importlib.util
import sqlite3
import tarfile
from pathlib import Path

import pytest
from PIL import Image

from studio.repositories.db import assets, engine_for, metadata
from studio.storage.images import save_image

spec = importlib.util.spec_from_file_location(
    "studio_backup", Path(__file__).parents[1] / "scripts" / "backup.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_backup_restores_database_and_referenced_images_only(tmp_path):
    root = tmp_path / "data"
    engine = engine_for(root)
    metadata.create_all(engine)
    item = save_image(root, Image.new("RGB", (8, 8), "red"), "test", True)
    with engine.begin() as conn:
        conn.execute(assets.insert().values(**item))
    (root / ".env").write_text("not-for-backup")
    (root / "assets" / "orphan.png").write_text("unreferenced")
    archive_path = module.backup(root, tmp_path / "backups")
    restored = tmp_path / "restored.db"
    with tarfile.open(archive_path) as archive:
        assert set(archive.getnames()) == {"studio.db", item["path"]}
        restored.write_bytes(archive.extractfile("studio.db").read())
        assert archive.extractfile(item["path"]).read() == (root / item["path"]).read_bytes()
    with sqlite3.connect(restored) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("SELECT id FROM assets").fetchone()[0] == item["id"]
    (root / item["path"]).unlink()
    with pytest.raises(FileNotFoundError):
        module.backup(root, tmp_path / "backups")
    assert not list((tmp_path / "backups").glob("*.partial"))
    assert len(list((tmp_path / "backups").glob("*.tar.gz"))) == 1
