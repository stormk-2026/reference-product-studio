import base64
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from test_real_providers import png, settings
from test_workflows import picture

from studio.domain.models import Request
from studio.providers.domestic import DomesticProvider
from studio.repositories.db import engine_for, metadata
from studio.services.workflow import Workflow
from studio.web.app import create_app
from studio.worker import run_once


@pytest.mark.parametrize("ratio", ["1:1", "3:4", "4:3", "4:5", "5:4", "2:3", "3:2", "9:16", "16:9"])
@pytest.mark.parametrize("execution", ["real", "fixture"])
def test_ratio_reaches_provider_and_export(tmp_path, monkeypatch, ratio, execution):
    config = settings(tmp_path)
    engine = engine_for(tmp_path)
    metadata.create_all(engine)
    workflow = Workflow(engine, tmp_path, settings=config)
    product = workflow.upload(picture(), "image/png", "比例测试", True)["id"]

    def respond(req):
        body = json.loads(req.content)
        assert f"目标画布比例 {ratio}" in body["prompt"]
        assert body["size"] == "2K"
        return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(png()).decode()}]})

    adapter = DomesticProvider(config, transport=httpx.MockTransport(respond))
    monkeypatch.setattr("studio.services.real_jobs.DomesticProvider", lambda _: adapter)
    request = Request(mode="A_white", execution=execution, product_ids=[product], ratio=ratio)
    token = workflow.preview(request)["confirmation_token"] if execution == "real" else None
    job = workflow.submit(request, "ratio-test", token)
    assert run_once(workflow)
    detail = workflow.detail(job["id"])
    assert detail["job"]["state"] == "succeeded", detail["job"]["error"]
    image = workflow.image(detail["candidate"]["asset_id"])
    width, height = map(int, ratio.split(":"))
    assert image.width * height == image.height * width
    assert detail["candidate"]["data"]["request"]["ratio"] == ratio
    if ratio == "9:16" and execution == "real":
        assert image.size == (1440, 2560)


def test_ratio_choices_match_request_schema(tmp_path):
    with TestClient(create_app(tmp_path), base_url="http://localhost") as client:
        page = client.get("/").text
    choices = Request.model_json_schema()["properties"]["ratio"]["enum"]
    for ratio in choices:
        assert f"<option>{ratio}</option>" in page
