import base64
import io
import json
import zipfile

import httpx
from fastapi.testclient import TestClient
from test_real_providers import png, settings
from test_workflows import picture

from studio.domain.models import ANALYSIS_FIELDS, RECIPE_FIELDS, Request
from studio.providers.domestic import DomesticProvider
from studio.repositories.db import engine_for, jobs, metadata
from studio.services.workflow import Workflow
from studio.web.app import create_app
from studio.worker import run_once


def test_domestic_full_worker_workflows_offline(tmp_path, monkeypatch):
    config = settings(tmp_path)
    engine = engine_for(tmp_path)
    metadata.create_all(engine)
    workflow = Workflow(engine, tmp_path, settings=config)
    product = workflow.upload(picture(), "image/png", "协议测试商品", True)["id"]
    reference = workflow.upload(picture(False), "image/png", "协议测试参考", True)["id"]
    calls = []

    def respond(req):
        body = json.loads(req.content)
        calls.append(body)
        if req.url.path.endswith("chat/completions"):
            if "通用电商商品视觉分析" in body["messages"][0]["content"]:
                content = {
                    "fields": {
                        name: {
                            "value": "电喷壶" if name == "商品类别" else None,
                            "status": "observed" if name == "商品类别" else "unknown",
                            "asset_ids": [product],
                            "note": "",
                        }
                        for name in ANALYSIS_FIELDS
                    },
                    "dimensions": [],
                    "workmanship": [],
                    "notes": "",
                    "generation_prompt": "白底商品摄影，展示主体外观与可见结构。",
                }
            else:
                content = {
                    "elements": {
                        key: {"value": None, "action": "inherit", "override": None}
                        for key in RECIPE_FIELDS
                    },
                    "preserve": "纽扣",
                    "exclude": "品牌",
                }
            return httpx.Response(
                200,
                json={
                    "id": "mock-kimi-request",
                    "model": "kimi-k3",
                    "usage": {"total_tokens": 20},
                    "choices": [
                        {"finish_reason": "stop", "message": {"content": json.dumps(content)}}
                    ],
                },
            )
        return httpx.Response(
            200,
            headers={"x-request-id": "mock-ark-request"},
            json={
                "model": config.seedream_model,
                "usage": {"generated_images": 1},
                "data": [{"b64_json": base64.b64encode(png()).decode()}],
            },
        )

    adapter = DomesticProvider(config, transport=httpx.MockTransport(respond))
    monkeypatch.setattr("studio.services.real_jobs.DomesticProvider", lambda settings: adapter)
    analysis_id = recipe_id = None
    for mode in ["A", "A_front", "A_back", "A_pattern", "B1", "B2", "C_analyze", "C1", "C2"]:
        request = Request(
            execution="real",
            mode=mode,
            product_ids=[product],
            reference_id=reference,
            analysis_id=analysis_id,
            recipe_id=recipe_id,
        )
        preview = workflow.preview(request)
        job = workflow.submit(request, mode, preview["confirmation_token"])
        assert run_once(workflow)
        result = workflow.detail(job["id"])
        assert result["job"]["state"] == "succeeded", result["job"]["error"]
        assert result["job"]["payload"]["receipt"]["usage"]
        if result["analysis"]:
            analysis_id = result["analysis"]["id"]
            assert not result["analysis"]["fixture"]
        if result["recipe"]:
            recipe_id = result["recipe"]["id"]
        if result["candidate"]:
            assert not result["candidate"]["fixture"]
            assert result["candidate"]["data"]["input_fixture"]
            assert result["candidate"]["data"]["provider_request_id"] == "mock-ark-request"
            with TestClient(create_app(tmp_path), base_url="http://localhost") as client:
                exported = client.get("/api/jobs/" + job["id"] + "/export")
                with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
                    assert "MODEL-result.png" in archive.namelist()
                    assert "FIXTURE-result.png" not in archive.namelist()
    assert len(calls) == 9


def test_preview_http_does_not_enqueue_or_expose_keys(tmp_path):
    engine = engine_for(tmp_path)
    metadata.create_all(engine)
    app = create_app(tmp_path)
    app.state.workflow.settings = settings(tmp_path)
    with TestClient(app, base_url="http://localhost") as client:
        token = client.get("/api/session").json()["csrf"]
        headers = {
            "origin": "http://localhost",
            "x-csrf-token": token,
            "idempotency-key": "real-web",
        }
        asset = app.state.workflow.upload(picture(), "image/png", "协议测试", True)["id"]
        payload = {"execution": "real", "mode": "A", "product_ids": [asset]}
        response = client.post("/api/jobs/preview", headers=headers, json=payload)
        assert response.status_code == 200
        assert "test-kimi" not in response.text and "test-ark" not in response.text
        assert app.state.workflow.list(jobs) == []
        assert client.post("/api/jobs", headers=headers, json=payload).status_code == 400
        headers["x-external-confirmation"] = response.json()["confirmation_token"]
        approved = client.post("/api/jobs", headers=headers, json=payload)
        assert approved.status_code == 200 and approved.json()["state"] == "queued"
