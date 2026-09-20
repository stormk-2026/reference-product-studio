import pytest
from pydantic import ValidationError
from test_real_providers import settings
from test_workflows import picture, upload

from studio.domain.models import Request
from studio.repositories.db import assets, engine_for, jobs, metadata
from studio.services.batch import preview_remaining, submit_remaining
from studio.services.external import external_plan
from studio.services.real_jobs import image_prompt
from studio.services.workflow import Workflow
from studio.worker import run_once


@pytest.fixture
def workflow(tmp_path):
    engine = engine_for(tmp_path)
    metadata.create_all(engine)
    return Workflow(engine, tmp_path)


def test_ten_inputs_and_optional_note(workflow):
    asset = workflow.upload(picture(), "image/png", "", False)
    assert asset["source"] == "未备注图片"
    assert len(Request(mode="A", product_ids=[str(i) for i in range(10)]).product_ids) == 10
    with pytest.raises(ValidationError):
        Request(mode="A", product_ids=[str(i) for i in range(11)])


def test_batch_gates_anchor_and_no_duplicate_after_completion(workflow):
    ids = [upload(workflow, False) for _ in range(3)]
    with pytest.raises(ValueError, match="首张"):
        workflow.prepare(
            Request(mode="B2", product_ids=[ids[1]], batch_product_ids=ids, batch_index=1)
        )
    first = workflow.submit(
        Request(mode="B2", product_ids=[ids[0]], batch_product_ids=ids), "first"
    )
    assert len(workflow.list(jobs)) == 1
    run_once(workflow)
    candidate = workflow.detail(first["id"])["candidate"]
    plan = preview_remaining(workflow, candidate["id"])
    assert len(workflow.list(jobs)) == 1  # Preview cannot enqueue remainder.
    assert len(plan["plans"]) == 2
    assert all(p["anchor_asset_id"] == candidate["asset_id"] for p in plan["plans"])
    with pytest.raises(ValueError):
        submit_remaining(workflow, candidate["id"], "invalid")
    rest = submit_remaining(workflow, candidate["id"], plan["confirmation_token"])
    while run_once(workflow):
        pass
    fresh = preview_remaining(workflow, candidate["id"])
    repeated = submit_remaining(workflow, candidate["id"], fresh["confirmation_token"])
    assert [j["id"] for j in rest] == [j["id"] for j in repeated]
    assert len(workflow.list(jobs)) == 3
    assert all(j["state"] == "succeeded" for j in repeated)


def test_mix_roles_are_explicit(workflow, tmp_path):
    a, subject, bg = [upload(workflow, False) for _ in range(3)]
    with pytest.raises(ValueError, match="自己的商品"):
        workflow.prepare(Request(mode="B2", product_ids=[a], change_subject=True))
    request = Request(
        mode="B2", product_ids=[a], change_subject=True, subject_id=subject, background_id=bg
    )
    plan = external_plan(request, settings(tmp_path))
    assert plan["sent_asset_ids"] == [a, subject, bg]
    prompt = image_prompt(request, workflow.prepare(request))
    assert "第二张" in prompt and "Logo" in prompt and "用户背景图" in prompt
    keep_bg = request.model_copy(update={"change_background": False, "background_id": None})
    assert "背景未勾选替换" in image_prompt(keep_bg, workflow.prepare(keep_bg))


def test_white_and_views_routes(workflow):
    a = upload(workflow, False)
    for mode in ["A_white", "A_views"]:
        request = Request(mode=mode, product_ids=[a])
        assert "商品" in image_prompt(request, workflow.prepare(request))
        job = workflow.submit(request, mode)
        run_once(workflow)
        assert workflow.detail(job["id"])["candidate"]


def test_white_requires_one_photo_and_preserves_its_view(workflow, tmp_path):
    a, b = upload(workflow, False), upload(workflow, False)
    with pytest.raises(ValueError, match="白底图仅使用 1 张"):
        workflow.prepare(Request(mode="A_white", product_ids=[a, b]))
    for field in ["back_id", "reference_id", "background_id", "subject_id", "mask_id"]:
        with pytest.raises(ValueError, match="不接受辅助角度"):
            workflow.prepare(Request(mode="A_white", product_ids=[a], **{field: b}))
    request = Request(mode="A_white", product_ids=[a])
    assert external_plan(request, settings(tmp_path))["sent_asset_ids"] == [a]
    prompt = image_prompt(request, workflow.prepare(request))
    assert "保持原图的观察视角" in prompt
    assert "不拼接正侧背面" in prompt
    assert "不补画不可见结构" in prompt
    # The single-photo restriction does not remove multi-view drawing support.
    workflow.prepare(Request(mode="A_views", product_ids=[a, b]))


def test_cutout_job_uses_local_mask_and_keeps_history(workflow, monkeypatch):
    from PIL import Image

    a = upload(workflow, False)
    calls = []

    def local(image, root):
        calls.append(image.size)
        result = image.copy()
        result.putalpha(Image.new("L", image.size, 128))
        return result

    monkeypatch.setattr("studio.services.cutout.remove_background", local)
    job = workflow.submit(Request(mode="CUTOUT", product_ids=[a]), "cut")
    run_once(workflow)
    detail = workflow.detail(job["id"])
    assert detail["candidate"]["data"]["provider"] == "local-rembg"
    assert calls == [(96, 96)]
    workflow.store.update(assets, a, {"hidden": True})
    assert workflow.image(a).size == (96, 96)
    assert workflow.detail(job["id"])["job"]["state"] == "succeeded"


def test_real_batch_anchor_is_sent_and_confirmation_is_bound(workflow, tmp_path):
    from studio.repositories.db import candidates

    workflow.settings = settings(tmp_path)
    ids = [upload(workflow, False) for _ in range(2)]
    first = workflow.submit(
        Request(mode="B2", product_ids=[ids[0]], batch_product_ids=ids), "anchor"
    )
    run_once(workflow)
    candidate = workflow.detail(first["id"])["candidate"]
    # Simulate a real provider completion without any network.
    original = workflow.get(jobs, first["id"])
    original["payload"]["request"]["execution"] = "real"
    workflow.store.update(jobs, first["id"], {"payload": original["payload"]})
    workflow.store.update(candidates, candidate["id"], {"fixture": False})
    plan = preview_remaining(workflow, candidate["id"])
    assert plan["max_calls"] == 1
    assert plan["plans"][0]["sent_asset_ids"] == [ids[1], candidate["asset_id"]]
    assert len(workflow.list(jobs)) == 1
    result = submit_remaining(workflow, candidate["id"], plan["confirmation_token"])
    assert result[0]["payload"]["external_authorized"]
    assert result[0]["payload"]["anchor_asset_id"] == candidate["asset_id"]


def test_multiview_sent_as_one_product_and_scene(workflow):
    ids = [upload(workflow, False) for _ in range(3)]
    req = Request(mode="B2", product_ids=[ids[0]], product_view_ids=[ids[1]], background_id=ids[2])
    plan = external_plan(req, settings(workflow.root))
    assert plan["sent_asset_ids"] == ids
    prepared = workflow.prepare(req)
    prompt = image_prompt(req, {**prepared, "sent_asset_ids": ids})
    assert "同一件商品的多角度" in prompt
    assert "第 3 张是目标背景" in prompt
    assert "只呈现一件商品" in prompt
    assert "背景颜色建议" not in prompt
    with pytest.raises(ValueError, match="不能同时批量"):
        workflow.prepare(req.model_copy(update={"batch_product_ids": [ids[0], ids[1]]}))
    with pytest.raises(ValueError, match="不能重复"):
        workflow.prepare(req.model_copy(update={"product_view_ids": [ids[0]]}))
