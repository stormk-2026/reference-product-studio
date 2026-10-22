import io
import json
import zipfile

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from studio.config import Settings
from studio.domain.content import ContentBrief, ContentDeck, ContentPage
from studio.domain.models import Request
from studio.providers.domestic import DomesticProvider, ProviderError
from studio.repositories.db import engine_for, metadata
from studio.services.content import fixture_deck, run_content
from studio.services.content_batch import preview_series, series_status, submit_series
from studio.services.content_render import render_deck
from studio.services.workflow import Workflow
from studio.web.app import create_app
from studio.worker import run_once


@pytest.fixture
def studio(tmp_path):
    engine = engine_for(tmp_path)
    metadata.create_all(engine)
    w = Workflow(
        engine,
        tmp_path,
        settings=Settings(
            storage_dir=tmp_path,
            moonshot_api_key="dummy",
            ark_api_key="dummy",
            seedream_model="doubao-seedream-5-0-pro-260628",
        ),
    )
    a = w.store_image(Image.new("RGB", (160, 320), "#226699"), "真实截图", False)
    b = ContentBrief(name="轻记账", facts="手动记账、分类汇总；不支持自动同步。")
    return w, a, b


def request(a, b, **kwargs):
    return Request(
        mode="CONTENT_COPY", product_ids=[a["id"]], ratio="3:4", content_brief=b, **kwargs
    )


@pytest.mark.parametrize("kind", ["app", "product"])
def test_plan_samples_full_export_and_restore(studio, monkeypatch, kind):
    w, a, b = studio
    b = b.model_copy(update={"kind": kind})
    job = w.submit(request(a, b), "copy")
    assert run_once(w)
    deck = ContentDeck.model_validate(w.detail(job["id"])["analysis"]["data"])
    for sample in (True, False):
        r = request(a, b).model_copy(
            update={"mode": "CONTENT_RENDER", "content_deck": deck, "content_sample": sample}
        )
        job = w.submit(r, "sample" if sample else "full")
        assert w.submit(r, "sample" if sample else "full")["id"] == job["id"]
        assert run_once(w)
        detail = w.detail(job["id"])
        assert detail["job"]["state"] == "succeeded"
        c = detail["candidate"]
        assert c["fixture"] is False  # Local rendering of real input is not a fake image generator.
        assert len(c["data"]["pages"]) == (2 if sample else 3)
        assert c["data"]["layout_check"]["text_overflow"] is False
        for aid in c["data"]["pages"]:
            assert w.image(aid).size == (1152, 1536)
        monkeypatch.setattr("studio.services.workflow.load_settings", lambda: w.settings)
        app = create_app(w.root)
        with TestClient(app, base_url="http://localhost") as client:
            restored = client.get("/api/jobs/" + job["id"]).json()
            assert restored["job"]["payload"]["request"]["content_deck"] == deck.model_dump()
            response = client.get("/api/jobs/" + job["id"] + "/export")
            with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
                assert len([n for n in archive.namelist() if n.endswith(".png")]) == len(
                    c["data"]["pages"]
                )
                assert archive.read("发布正文.txt").decode().endswith(deck.post_body)


def test_copy_signature_receipt_and_no_retry(studio):
    w, a, b = studio
    r = request(a, b, execution="real")
    preview = w.preview(r)
    assert preview["plan"]["provider"] == "moonshot"
    assert preview["plan"]["max_calls"] == 1 and preview["plan"]["max_output_images"] == 0
    assert preview["compiled_prompt"] is None
    with pytest.raises(ValueError):
        w.submit(r, "no-consent")
    changed = r.model_copy(update={"content_brief": b.model_copy(update={"name": "另一个产品"})})
    with pytest.raises(ValueError):
        w.submit(changed, "tamper", preview["confirmation_token"])
    job = w.submit(r, "real", preview["confirmation_token"])
    assert w.submit(r, "duplicate", preview["confirmation_token"])["id"] == job["id"]
    calls = []
    deck = fixture_deck(b, 1)

    def respond(req):
        body = json.loads(req.content)
        calls.append(body)
        assert "不能访问网络" in body["messages"][0]["content"]
        return httpx.Response(
            200,
            json={
                "model": "kimi-k3",
                "id": "safe-id",
                "choices": [
                    {"finish_reason": "stop", "message": {"content": deck.model_dump_json()}}
                ],
                "usage": {"total_tokens": 30},
            },
        )

    provider = DomesticProvider(w.settings, transport=httpx.MockTransport(respond))
    claimed = w.store.claim()
    run_content(w, claimed, provider)
    detail = w.detail(job["id"])
    assert len(calls) == 1 and detail["job"]["state"] == "succeeded"
    assert detail["job"]["payload"]["receipt"]["usage"]["total_tokens"] == 30


def test_rejects_unsupported_inputs_and_deck(studio):
    w, a, b = studio
    r = request(a, b)
    for update in ({"background_id": a["id"]}, {"ratio": "9:16"}, {"product_ids": [a["id"]] * 7}):
        with pytest.raises(ValueError):
            w.prepare(r.model_copy(update=update))
    deck = fixture_deck(b, 1)
    deck.pages[1].image_index = 2
    with pytest.raises(ValueError, match="未选择"):
        w.prepare(r.model_copy(update={"mode": "CONTENT_RENDER", "content_deck": deck}))
    with pytest.raises(ValueError, match="本地执行"):
        w.prepare(
            r.model_copy(
                update={"mode": "CONTENT_RENDER", "content_deck": deck, "execution": "real"}
            )
        )


def test_whole_deck_tokens_and_overflow(studio):
    _, _, b = studio
    b = b.model_copy(update={"page_count": 6})
    deck = ContentDeck(
        pages=[
            ContentPage(
                label="使用场景",
                title="完整保留真实截图内容，使用统一层级介绍产品亮点",
                body="这是用户填写的真实功能与说明。" * 10,
            )
            for _ in range(6)
        ],
        post_title="产品介绍",
        post_body="用户确认的正文",
    )
    images, qa = render_deck(b, deck, [Image.new("RGB", (800, 1600), "red")])
    assert len(images) == 6 and qa["title_size"] in (56, 64, 72)
    assert all(i.size == (1152, 1536) for i in images)
    deck.pages[-1].body = "\n".join(["内容"] * 8)
    with pytest.raises(ValueError, match="超出"):
        render_deck(b, deck, [Image.new("RGB", (50, 50))])


def test_provider_rejects_out_of_range_image_and_preserves_receipt(studio):
    w, _, b = studio
    deck = fixture_deck(b, 1)
    deck.pages[1].image_index = 5

    def respond(req):
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"finish_reason": "stop", "message": {"content": deck.model_dump_json()}}
                ]
            },
        )

    received = []
    provider = DomesticProvider(w.settings, transport=httpx.MockTransport(respond))
    with pytest.raises(ProviderError):
        provider.analyze("CONTENT_COPY", [b"fake-image"], ["only-one"], "", received.append)
    assert received


def test_received_wrong_page_count_is_failed_not_unknown(studio, monkeypatch):
    from types import SimpleNamespace

    w, a, b = studio
    r = request(a, b, execution="real")
    preview = w.preview(r)
    job = w.submit(r, "wrong-page-count", preview["confirmation_token"])
    wrong = fixture_deck(b.model_copy(update={"page_count": 4}), 1)

    class Provider:
        def analyze(self, mode, images, ids, prompt, received):
            received({"provider_request_id": "received-copy", "usage": {"total_tokens": 30}})
            return SimpleNamespace(value=wrong)

    monkeypatch.setattr("studio.services.content.DomesticProvider", lambda _: Provider())
    assert run_once(w)
    detail = w.detail(job["id"])
    assert detail["job"]["state"] == "failed"
    assert detail["job"]["phase"] == "received"
    assert "未自动重试" in detail["job"]["error"]
    assert not run_once(w)


def test_polish_preserves_original_and_does_not_send_images(studio):
    from types import SimpleNamespace

    w, a, b = studio
    original = fixture_deck(b, 1)
    polished = original.model_copy(deep=True)
    polished.pages[0].title = "更清楚的标题"
    r = request(a, b, execution="real").model_copy(
        update={
            "mode": "CONTENT_POLISH",
            "content_deck": original,
            "content_polish_note": "更口语化",
            "execution": "real",
        }
    )
    preview = w.preview(r)
    assert preview["sent_assets"] == []
    assert preview["plan"]["max_calls"] == 1
    job = w.submit(r, "polish", preview["confirmation_token"])

    class Provider:
        def analyze(self, mode, images, ids, prompt, received):
            assert mode == "CONTENT_POLISH" and images == [] and ids == []
            assert "original_deck" in prompt and "更口语化" in prompt
            received({"provider_request_id": "polished", "usage": {"total_tokens": 20}})
            return SimpleNamespace(value=polished)

    run_content(w, w.store.claim(), Provider())
    detail = w.detail(job["id"])
    assert detail["analysis"]["data"]["pages"][0]["title"] == "更清楚的标题"
    assert detail["job"]["payload"]["request"]["content_deck"] == original.model_dump()


def test_seedream_visual_page_and_approved_remaining(studio):
    from types import SimpleNamespace

    w, a, b = studio
    deck = fixture_deck(b, 1)
    r = request(a, b, execution="real").model_copy(
        update={
            "mode": "CONTENT_SCENE",
            "content_deck": deck,
            "execution": "real",
        }
    )
    preview = w.preview(r)
    assert preview["plan"]["provider"] == "volcengine"
    assert preview["plan"]["max_calls"] == 1
    assert preview["sent_assets"] == []
    assert "不要纯色白图" in preview["plan"]["prompt"]
    first_job = w.submit(r, "first", preview["confirmation_token"])

    class Provider:
        def __init__(self):
            self.calls = []

        def render(self, images, prompt, ratio, received):
            self.calls.append((images, prompt, ratio))
            received({"provider_request_id": "rendered", "usage": {"total_tokens": 0}})
            return SimpleNamespace(image=Image.new("RGB", (1152, 1536), "#ab8764"))

    provider = Provider()
    run_content(w, w.store.claim(), provider)
    first = w.detail(first_job["id"])["candidate"]
    assert len(provider.calls) == 1 and provider.calls[0][0] == []
    assert w.image(first["asset_id"]).size == (1152, 1536)
    assert first["data"]["background_asset_id"] != first["asset_id"]
    with pytest.raises(ValueError, match="首页"):
        w.prepare(r.model_copy(update={"content_page_index": 1}))
    batch = preview_series(w, first["id"])
    assert batch["max_calls"] == 2
    assert all(
        p["sent_asset_ids"] == [first["data"]["background_asset_id"]] for p in batch["plans"]
    )
    with pytest.raises(ValueError):
        submit_series(w, first["id"], "bad")
    created = submit_series(w, first["id"], batch["confirmation_token"])
    assert [x["state"] for x in created] == ["queued", "queued"]
    assert [x["id"] for x in submit_series(w, first["id"], batch["confirmation_token"])] == [
        x["id"] for x in created
    ]
    while (claimed := w.store.claim()) is not None:
        run_content(w, claimed, provider)
    status = series_status(w, first["id"])
    assert status["complete"] and len(provider.calls) == 3
    assert all(len(call[0]) == 1 for call in provider.calls[1:])
