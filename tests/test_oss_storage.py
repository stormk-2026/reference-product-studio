import base64
import importlib.util
import io
import sqlite3
import tarfile
import zipfile
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from studio.config import Settings
from studio.domain.models import Request
from studio.providers.domestic import DomesticProvider
from studio.repositories.db import assets, engine_for, metadata
from studio.services.workflow import Workflow
from studio.storage.backend import AssetStorage, StorageError
from studio.storage.images import save_image
from studio.web.app import create_app
from studio.worker import run_once


class Body(io.BytesIO):
    def iter_bytes(self):
        yield self.read()


class FakeOSS:
    def __init__(self):
        self.objects, self.puts = {}, []
        self.fail = False

    def put_object(self, request):
        if self.fail:
            raise RuntimeError("credential=must-not-leak")
        self.puts.append(request)
        self.objects[request.key] = request.body

    def get_object(self, request):
        if self.fail:
            raise RuntimeError("credential=must-not-leak")
        return SimpleNamespace(body=Body(self.objects[request.key]))


def settings(root, **changes):
    return Settings(
        storage_dir=root,
        asset_backend="oss",
        oss_bucket="studio-test-bucket",
        oss_access_key_id="test-only-id",
        oss_access_key_secret="test-only-secret",
        **changes,
    )


@pytest.fixture
def remote(tmp_path, monkeypatch):
    fake = FakeOSS()
    monkeypatch.setattr(AssetStorage, "client", lambda self: fake)
    engine = engine_for(tmp_path)
    metadata.create_all(engine)
    return Workflow(engine, tmp_path, settings=settings(tmp_path)), fake


@pytest.mark.parametrize("mode", ["A_white", "A_views", "B2"])
def test_oss_workflows_download_and_export_without_local_images(remote, monkeypatch, mode):
    workflow, fake = remote
    # create_app exposes its workflow so both web and worker use the same storage configuration.
    monkeypatch.setattr("studio.services.workflow.load_settings", lambda: workflow.settings)
    app = create_app(workflow.root)
    product = workflow.store_image(Image.new("RGB", (32, 32), "red"), "商品", True)
    background = workflow.store_image(Image.new("RGB", (32, 32), "blue"), "场景", True)
    request = Request(
        mode=mode,
        product_ids=[product["id"]],
        background_id=background["id"] if mode == "B2" else None,
    )
    job = workflow.submit(request, "oss-" + mode)
    run_once(workflow)
    detail = workflow.detail(job["id"])
    assert detail["job"]["state"] == "succeeded"
    assert not (workflow.root / "assets").exists()
    assert all(p.acl == "private" and p.forbid_overwrite is True for p in fake.puts)
    with TestClient(app, base_url="http://localhost") as client:
        result = client.get("/api/assets/" + detail["candidate"]["asset_id"] + "?download=true")
        assert result.status_code == 200
        assert "attachment" in result.headers["content-disposition"]
        assert Image.open(io.BytesIO(result.content)).format == "PNG"
        export = client.get("/api/jobs/" + job["id"] + "/export")
        assert export.status_code == 200
        with zipfile.ZipFile(io.BytesIO(export.content)) as archive:
            assert archive.read("FIXTURE-result.png") == result.content
        fake.fail = True
        failure = client.get("/api/assets/" + product["id"])
        assert failure.status_code == 503
        assert "must-not-leak" not in failure.text


def test_legacy_local_reads_and_failed_upload_does_not_insert(remote):
    workflow, fake = remote
    local = save_image(workflow.root, Image.new("RGB", (8, 8)), "legacy", True)
    workflow.store.insert(assets, local)
    assert workflow.image(local["id"]).size == (8, 8)
    fake.fail = True
    with pytest.raises(StorageError, match="OSS 上传失败") as error:
        workflow.store_image(Image.new("RGB", (8, 8)), "failed", True)
    assert "must-not-leak" not in str(error.value)
    assert len(workflow.list(assets)) == 1


def test_received_generation_is_preserved_locally_if_oss_is_down(remote):
    workflow, fake = remote
    fake.fail = True
    item = workflow.store_image(
        Image.new("RGB", (8, 8), "red"),
        "模型结果",
        False,
        preserve_on_storage_failure=True,
    )
    assert item["path"].startswith("assets/")
    assert "OSS 写入失败" in item["source"]
    assert workflow.image(item["id"]).size == (8, 8)


def test_paid_response_survives_oss_failure_without_regeneration(remote, monkeypatch):
    from test_real_providers import png
    from test_real_providers import settings as provider_settings

    workflow, fake = remote
    workflow.settings = provider_settings(workflow.root).model_copy(update={"asset_backend": "oss"})
    product = workflow.store_image(Image.new("RGB", (8, 8)), "商品", True)
    calls = []

    def respond(request):
        calls.append(request)
        fake.fail = True  # Storage goes down after inputs have been sent to the model.
        return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(png()).decode()}]})

    adapter = DomesticProvider(workflow.settings, transport=httpx.MockTransport(respond))
    monkeypatch.setattr("studio.services.real_jobs.DomesticProvider", lambda settings: adapter)
    request = Request(mode="A_white", execution="real", product_ids=[product["id"]])
    preview = workflow.preview(request)
    job = workflow.submit(request, "storage-outage", preview["confirmation_token"])
    assert run_once(workflow)
    detail = workflow.detail(job["id"])
    assert detail["job"]["state"] == "succeeded"
    assert len(calls) == 1
    assert "OSS 写入失败" in detail["candidate"]["data"]["warning"]
    assert workflow.image(detail["candidate"]["asset_id"]).width > 0


def test_official_sdk_client_builds_without_global_credentials(tmp_path):
    storage = AssetStorage(tmp_path, settings(tmp_path))
    assert storage.client() is storage.client()
    assert "test-only-secret" not in repr(storage.settings)
    assert "oss_access_key_secret" not in storage.settings.model_dump()


def test_oss_scope_and_integrity(remote):
    workflow, fake = remote
    item = workflow.store_image(Image.new("RGB", (8, 8)), "test", True)
    for path in [
        "oss://another-bucket/storm-studio/assets/" + item["id"] + ".png",
        item["path"].replace("storm-studio/", "other-app/"),
        item["path"].replace(item["id"], "../secret"),
    ]:
        with pytest.raises(StorageError):
            workflow.storage.read(path)
    fake.objects[workflow.storage.oss_key(item["path"])] = b"tampered"
    with pytest.raises(StorageError, match="校验失败"):
        workflow.image(item["id"])


@pytest.mark.parametrize(
    "changes",
    [dict(oss_endpoint="https://evil.example"), dict(oss_prefix=""), dict(oss_prefix="../a/")],
)
def test_invalid_oss_configuration_fails_closed(tmp_path, changes):
    with pytest.raises(StorageError):
        AssetStorage(tmp_path, settings(tmp_path, **changes))


def test_oss_backup_restores_offline_without_cloud_access(remote, tmp_path):
    workflow, fake = remote
    item = workflow.store_image(Image.new("RGB", (8, 8), "green"), "cloud", True)
    spec = importlib.util.spec_from_file_location(
        "backup_oss", Path(__file__).parents[1] / "scripts/backup.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.backup(workflow.root, tmp_path / "backups", storage=workflow.storage)
    restored = tmp_path / "restore"
    restored.mkdir()
    with tarfile.open(result) as archive:
        archive.extractall(restored, filter="data")
    with sqlite3.connect(restored / "studio.db") as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("SELECT path FROM assets").fetchone()[0] == f"assets/{item['id']}.png"
    local = Workflow(engine_for(restored), restored, settings=Settings(storage_dir=restored))
    fake.fail = True
    assert local.image(item["id"]).size == (8, 8)
    # The live database keeps its OSS location; the backup operation is read-only.
    assert workflow.get(assets, item["id"])["path"].startswith("oss://")
