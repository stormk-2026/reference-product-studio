import io
import json
import zipfile
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from test_workflows import picture

from studio.domain.models import Request
from studio.repositories.db import analyses, engine_for, jobs, metadata, now
from studio.services.composite import composite
from studio.services.workflow import Workflow
from studio.storage import images
from studio.web.app import create_app
from studio.worker import claim, recover, run_once


def setup(tmp_path):
    engine = engine_for(tmp_path)
    metadata.create_all(engine)
    workflow = Workflow(engine, tmp_path)
    asset = workflow.upload(picture(), "image/png", "测试", True)
    return workflow, asset["id"]


def test_b1_pixels_with_identity_scale_and_background():
    subject = Image.new("RGBA", (20, 20), (12, 34, 56, 255))
    subject.putpixel((0, 0), (0, 0, 0, 0))
    background = Image.new("RGBA", (40, 132), (210, 211, 212, 255))
    request = Request(mode="B1", product_ids=["x"], scale=0.5, shadow=False, x=0, y=0)
    result, history = composite(subject, background, request)
    assert result.getpixel((5, 97)) == (12, 34, 56, 255)
    assert result.getpixel((0, 92)) == (210, 211, 212, 255)
    assert result.getpixel((30, 100)) == (210, 211, 212, 255)
    assert any("重采样" in entry for entry in history)


def test_file_limits_reject_before_storage(monkeypatch):
    monkeypatch.setattr(images, "MAX_BYTES", 5)
    with pytest.raises(ValueError, match="15 MB"):
        images.decode(picture(), "image/png")
    monkeypatch.setattr(images, "MAX_BYTES", 1_000_000)
    monkeypatch.setattr(images, "MAX_PIXELS", 10)
    with pytest.raises(ValueError, match="像素"):
        images.decode(picture(), "image/png")


def test_atomic_claim_and_recovery(tmp_path):
    workflow, asset = setup(tmp_path)
    first = workflow.submit(Request(mode="A", product_ids=[asset]), "first")
    with ThreadPoolExecutor(2) as pool:
        claims = list(pool.map(lambda _: claim(workflow), range(2)))
    assert sum(c is not None for c in claims) == 1
    recover(workflow)
    assert workflow.get(jobs, first["id"])["state"] == "interrupted"
    other = workflow.submit(Request(mode="B2", product_ids=[asset]), "second")
    claim(workflow)
    with workflow.engine.begin() as conn:
        conn.execute(
            jobs.update()
            .where(jobs.c.id == other["id"])
            .values(phase="dispatching", lease_until=now() - 10)
        )
    recover(workflow)
    assert workflow.get(jobs, other["id"])["state"] == "outcome_unknown"
    assert claim(workflow) is None


def test_analysis_edits_do_not_change_candidate_snapshot(tmp_path):
    workflow, asset = setup(tmp_path)
    job = workflow.submit(Request(mode="A", product_ids=[asset]), "analysis")
    run_once(workflow)
    record = workflow.detail(job["id"])["analysis"]
    candidate_job = workflow.submit(
        Request(mode="A_front", product_ids=[asset], analysis_id=record["id"]), "front"
    )
    changed = json.loads(json.dumps(record["data"]))
    changed["fields"]["商品类别"] = {
        "value": "夹克",
        "status": "user_confirmed",
        "asset_ids": [asset],
        "note": "",
    }
    saved = workflow.edit("analysis", record["id"], changed, 1)
    assert saved["version"] == 2
    assert workflow.get(analyses, record["id"])["data"]["fields"]["商品类别"]["value"] is None
    run_once(workflow)
    assert (
        workflow.detail(candidate_job["id"])["candidate"]["data"]["analysis"]["fields"]["商品类别"][
            "value"
        ]
        is None
    )
    with pytest.raises(ValueError, match="新版本"):
        workflow.edit("analysis", record["id"], changed, 1)


def test_zip_has_fixture_warning_and_viewable_image(tmp_path):
    workflow, asset = setup(tmp_path)
    job = workflow.submit(Request(mode="A_pattern", product_ids=[asset]), "pattern")
    run_once(workflow)
    with TestClient(create_app(tmp_path), base_url="http://localhost") as client:
        response = client.get(f"/api/jobs/{job['id']}/export")
        assert response.status_code == 200
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            assert "不可直接裁剪生产" in archive.read("READ-ME.txt").decode()
            manifest = json.loads(archive.read("FIXTURE-manifest.json"))
            assert manifest["result"]["candidate"]["fixture"]
            Image.open(io.BytesIO(archive.read("FIXTURE-result.png"))).verify()


def test_preserve_is_compiled_for_image_requests(tmp_path):
    workflow, asset = setup(tmp_path)
    job = workflow.submit(
        Request(mode="C1", product_ids=[asset], reference_id=asset, preserve="保留六颗纽扣"),
        "preserve",
    )
    assert "保留六颗纽扣" in job["payload"]["prompt"]
