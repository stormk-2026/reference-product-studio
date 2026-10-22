import pytest
from fastapi.testclient import TestClient
from test_workflows import upload

from studio.domain.content import ContentBrief
from studio.domain.models import Request
from studio.repositories.db import engine_for, metadata
from studio.services.workflow import Workflow
from studio.web.app import create_app
from studio.worker import run_once


def test_public_origin_secure_cookie_and_cross_site_rejection(tmp_path):
    metadata.create_all(engine_for(tmp_path))
    with TestClient(create_app(tmp_path), base_url="https://stormstudio.top") as client:
        session = client.get("/api/session")
        assert "Secure" in session.headers["set-cookie"]
        token = session.json()["csrf"]
        headers = {"origin": "https://stormstudio.top", "x-csrf-token": token}
        # Missing upload produces validation error, proving CSRF accepted this origin.
        assert client.post("/api/assets", headers=headers).status_code == 422
        for origin in ("https://evil.example", "http://stormstudio.top"):
            headers["origin"] = origin
            assert client.post("/api/assets", headers=headers).status_code == 403
        assert (
            client.post("/api/assets", headers={"origin": "https://stormstudio.top"}).status_code
            == 403
        )
        page = client.get("/").text
        assert "浙ICP备2026082439号-1" in page
        assert 'href="https://beian.miit.gov.cn/"' in page


@pytest.mark.parametrize("kind", ["app", "product"])
def test_content_fixture_copy_and_invalid_asset_reference(tmp_path, kind):
    engine = engine_for(tmp_path)
    metadata.create_all(engine)
    workflow = Workflow(engine, tmp_path)
    product = upload(workflow)
    brief = ContentBrief(kind=kind, name="示例产品", facts="用户提供的真实卖点")
    request = Request(mode="CONTENT_COPY", product_ids=[product], content_brief=brief, ratio="3:4")
    job = workflow.submit(request, "content-copy")
    assert run_once(workflow)
    detail = workflow.detail(job["id"])
    assert detail["job"]["state"] == "succeeded"
    assert detail["analysis"]["fixture"]
    deck = detail["analysis"]["data"]
    assert len(deck["pages"]) == 3
    deck["pages"][0]["image_index"] = 1
    render = Request(
        mode="CONTENT_RENDER",
        product_ids=[product],
        content_brief=brief,
        content_deck=deck,
        ratio="3:4",
    )
    with pytest.raises(ValueError, match="未选择的图片"):
        workflow.submit(render, "invalid-reference")
