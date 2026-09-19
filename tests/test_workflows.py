import io
from concurrent.futures import ThreadPoolExecutor

import pytest
from PIL import Image
from sqlalchemy import select

from studio.domain.models import Request
from studio.repositories.db import assets, candidates, engine_for, jobs, metadata
from studio.services.workflow import Workflow
from studio.storage.images import decode, safe_path
from studio.worker import run_once


@pytest.fixture
def workflow(tmp_path):
    engine = engine_for(tmp_path)
    metadata.create_all(engine)
    return Workflow(engine, tmp_path)


def picture(alpha=True):
    im = Image.new("RGBA", (96, 96), (0, 0, 0, 0) if alpha else (245, 245, 245, 255))
    for x in range(24, 72):
        for y in range(24, 72):
            im.putpixel((x, y), (190, 40, 25, 255))
    out = io.BytesIO()
    im.save(out, format="PNG")
    return out.getvalue()


def upload(workflow, alpha=True):
    return workflow.upload(picture(alpha), "image/png", "本地合成测试图", True)["id"]


def test_security_decode_and_path(tmp_path):
    with pytest.raises(ValueError):
        decode(b"<svg/>", "image/png")
    with pytest.raises(ValueError):
        decode(picture(), "image/jpeg")
    with pytest.raises(ValueError):
        safe_path(tmp_path, "../outside.png")


def test_idempotency_and_conflict(workflow):
    product = upload(workflow)
    request = Request(mode="A", product_ids=[product])
    with ThreadPoolExecutor(4) as pool:
        ids = list(pool.map(lambda _: workflow.submit(request, "same-key")["id"], range(4)))
    assert len(set(ids)) == 1
    with pytest.raises(ValueError, match="幂等"):
        workflow.submit(Request(mode="B2", product_ids=[product]), "same-key")


def test_b1_opaque_requires_mask_or_transparency(workflow):
    with pytest.raises(ValueError, match="透明"):
        workflow.submit(Request(mode="B1", product_ids=[upload(workflow, False)]), "opaque")


def test_all_routes_have_real_files_and_fixture_provenance(workflow):
    product, ref = upload(workflow), upload(workflow, False)
    analysis_id = recipe_id = None
    for mode in ["A", "A_front", "A_back", "A_pattern", "B1", "B2", "C_analyze", "C1", "C2"]:
        request = Request(
            mode=mode,
            product_ids=[product],
            reference_id=ref,
            analysis_id=analysis_id,
            recipe_id=recipe_id,
        )
        job = workflow.submit(request, mode)
        assert run_once(workflow)
        detail = workflow.detail(job["id"])
        assert detail["job"]["state"] == "succeeded", detail
        if mode == "A":
            analysis_id = detail["analysis"]["id"]
            assert all(
                x["status"] == "unknown" for x in detail["analysis"]["data"]["fields"].values()
            )
        elif mode == "C_analyze":
            recipe_id = detail["recipe"]["id"]
        else:
            candidate = detail["candidate"]
            assert candidate["fixture"]
            assert candidate["data"]["cost_estimate"] is None
            assert candidate["data"]["provider"] == "fixture"
            asset = workflow.get(assets, candidate["asset_id"])
            with Image.open(safe_path(workflow.root, asset["path"])) as result:
                result.verify()
            if mode == "A_pattern":
                assert "不可直接裁剪生产" in candidate["data"]["warning"]
            if mode == "A_back":
                assert "设计假设" in candidate["data"]["label"]


def test_worker_failure_is_persisted(workflow, monkeypatch):
    job = workflow.submit(Request(mode="B2", product_ids=[upload(workflow)]), "failure")

    def broken(*args):
        raise TimeoutError("simulated timeout")

    monkeypatch.setattr(workflow.provider, "render", broken)
    run_once(workflow)
    assert workflow.get(jobs, job["id"])["state"] == "outcome_unknown"
    assert not run_once(workflow)
    with workflow.engine.connect() as connection:
        assert connection.execute(select(candidates)).first() is None


def test_recipe_required(workflow):
    with pytest.raises(ValueError, match="配方"):
        workflow.submit(
            Request(mode="C2", product_ids=[upload(workflow)], reference_id=upload(workflow)),
            "missing",
        )
