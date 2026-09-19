import base64
import io
import json

import httpx
import pytest
from PIL import Image
from pydantic import SecretStr

from studio.config import Settings
from studio.domain.models import ANALYSIS_FIELDS, Request
from studio.providers.domestic import DomesticProvider, ProviderError
from studio.services.external import external_plan


def settings(tmp_path):
    return Settings(
        storage_dir=tmp_path,
        moonshot_api_key=SecretStr("test-kimi"),
        ark_api_key=SecretStr("test-ark"),
        seedream_model="doubao-seedream-5-0-pro-260628",
    )


def png():
    buffer = io.BytesIO()
    Image.new("RGB", (32, 32), "green").save(buffer, "PNG")
    return buffer.getvalue()


def test_send_lists_and_no_mask_degradation(tmp_path):
    config = settings(tmp_path)
    plan = external_plan(
        Request(mode="C2", product_ids=["p"], reference_id="r", strategy="text_only"), config
    )
    assert plan["sent_asset_ids"] == ["p"]
    assert external_plan(Request(mode="C_analyze", product_ids=["p"], reference_id="r"), config)[
        "sent_asset_ids"
    ] == ["r"]
    assert (
        external_plan(Request(mode="B1", product_ids=["p"], mask_id="m"), config)["sent_asset_ids"]
        == []
    )
    with pytest.raises(ValueError, match="蒙版"):
        external_plan(Request(mode="B2", product_ids=["p"], mask_id="m"), config)


def test_kimi_parse_and_evidence_boundary(tmp_path):
    observed = {
        "fields": {
            k: {"value": None, "status": "unknown", "asset_ids": ["p"], "note": ""}
            for k in ANALYSIS_FIELDS
        },
        "dimensions": [],
        "workmanship": [],
        "notes": "",
        "generation_prompt": "白底商品摄影，展示主体外观与可见结构。",
    }
    observed["fields"]["商品类别"]["status"] = "user_confirmed"
    observed["fields"]["商品类别"]["value"] = "shirt"

    def handle(req):
        body = json.loads(req.content)
        assert body["model"] == "kimi-k3"
        assert body["messages"][1]["content"][0]["image_url"]["url"].startswith(
            "data:image/png;base64,"
        )
        return httpx.Response(
            200,
            json={
                "id": "request-1",
                "model": "kimi-k3",
                "usage": {"total_tokens": 19},
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps(observed),
                            "reasoning_content": "ignore this",
                        },
                    }
                ],
            },
        )

    provider = DomesticProvider(settings(tmp_path), transport=httpx.MockTransport(handle))
    with pytest.raises(ProviderError, match="结构化"):
        provider.analyze("A", [png()], ["p"], "", lambda receipt: None)


def test_seedream_native_payload_and_decode(tmp_path):
    def handle(req):
        body = json.loads(req.content)
        assert req.url.path == "/api/v3/images/generations"
        assert body["response_format"] == "b64_json"
        assert "sequential_image_generation" not in body
        assert "stream" not in body
        assert body["output_format"] == "png"
        assert body["watermark"] is True
        assert len(body["image"]) == 2
        return httpx.Response(
            200,
            headers={"x-request-id": "req-image"},
            json={
                "model": "doubao-seedream-5-0-pro-260628",
                "data": [{"b64_json": base64.b64encode(png()).decode()}],
                "usage": {"generated_images": 1},
            },
        )

    provider = DomesticProvider(settings(tmp_path), transport=httpx.MockTransport(handle))
    result = provider.render([png(), png()], "test", "1:1", lambda receipt: None)
    assert result.image.size == (32, 32)
    assert result.receipt["provider_request_id"] == "req-image"


@pytest.mark.parametrize(
    "code,state",
    [(401, "failed"), (429, "failed"), (500, "outcome_unknown"), (302, "outcome_unknown")],
)
def test_errors_redacted_no_retry(tmp_path, code, state):
    calls = []

    def handle(req):
        calls.append(req)
        return httpx.Response(code, json={"error": {"message": "test-ark signed-url-secret"}})

    provider = DomesticProvider(settings(tmp_path), transport=httpx.MockTransport(handle))
    with pytest.raises(ProviderError) as caught:
        provider.render([], "test", "1:1", lambda receipt: None)
    assert len(calls) == 1 and caught.value.state == state
    assert "secret" not in str(caught.value) and "test-ark" not in str(caught.value)


def test_url_only_response_never_downloaded(tmp_path):
    calls = []

    def handle(req):
        calls.append(req)
        return httpx.Response(200, json={"data": [{"url": "http://127.0.0.1/private"}]})

    with pytest.raises(ProviderError, match="Base64"):
        DomesticProvider(settings(tmp_path), transport=httpx.MockTransport(handle)).render(
            [], "x", "1:1", lambda r: None
        )
    assert len(calls) == 1


def test_model_mismatch_not_silently_accepted(tmp_path):
    response = {"model": "another-model", "data": [{"b64_json": base64.b64encode(png()).decode()}]}
    provider = DomesticProvider(
        settings(tmp_path),
        transport=httpx.MockTransport(lambda req: httpx.Response(200, json=response)),
    )
    with pytest.raises(ProviderError, match="型号"):
        provider.render([], "test", "1:1", lambda r: None)


@pytest.mark.parametrize("error", [httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout])
def test_connection_failure_is_not_sent(tmp_path, error):
    calls = []

    def handle(req):
        calls.append(req)
        raise error("test-ark private details", request=req)

    provider = DomesticProvider(settings(tmp_path), transport=httpx.MockTransport(handle))
    with pytest.raises(ProviderError) as caught:
        provider.render([], "test", "1:1", lambda r: None)
    assert caught.value.state == "failed" and len(calls) == 1
    assert "未发送模型请求" in str(caught.value)
    assert "test-ark" not in str(caught.value)


def test_timeout_is_unknown_and_not_retried(tmp_path):
    calls = []

    def handle(req):
        calls.append(req)
        raise httpx.ReadTimeout("test-ark private details", request=req)

    provider = DomesticProvider(settings(tmp_path), transport=httpx.MockTransport(handle))
    with pytest.raises(ProviderError) as caught:
        provider.render([], "test", "1:1", lambda r: None)
    assert caught.value.state == "outcome_unknown" and len(calls) == 1
    assert "test-ark" not in str(caught.value)


@pytest.mark.parametrize(
    "category,attribute", [("电喷壶", "喷头结构"), ("运动鞋", "鞋底纹理"), ("台灯", "灯臂结构")]
)
def test_analysis_fields_follow_product_category(tmp_path, category, attribute):
    def handle(req):
        system = json.loads(req.content)["messages"][0]["content"]
        assert "动态生成" in system and "服装款式分析" not in system
        content = {
            "fields": {
                "商品类别": {"value": category, "status": "inferred", "asset_ids": ["p"]},
                attribute: {
                    "value": "可见结构描述",
                    "status": "observed",
                    "asset_ids": ["p"],
                    "note": "来自商品图片",
                },
            },
            "notes": "按当前品类描述商品",
            "generation_prompt": "商品摄影，" + category + "，展示" + attribute,
        }
        return httpx.Response(
            200,
            json={
                "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(content)}}]
            },
        )

    result = DomesticProvider(settings(tmp_path), transport=httpx.MockTransport(handle)).analyze(
        "A", [png()], ["p"], "", lambda r: None
    )
    assert set(result.value.fields) == {"商品类别", attribute}
    assert "领型" not in result.value.fields


def test_empty_analysis_not_marked_success(tmp_path):
    content = {
        "generation_prompt": "商品图",
        "fields": {"商品类别": {"value": None, "status": "unknown"}},
    }
    response = {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(content)}}]}
    provider = DomesticProvider(
        settings(tmp_path),
        transport=httpx.MockTransport(lambda req: httpx.Response(200, json=response)),
    )
    with pytest.raises(ProviderError, match="未提供有效商品属性"):
        provider.analyze("A", [png()], ["p"], "", lambda r: None)


def test_redraw_preserves_product_without_cutout():
    from studio.services.real_jobs import image_prompt

    request = Request(mode="B2", product_ids=["opaque-product"], instructions="替换为花园背景")
    prompt = image_prompt(request, {"prompt": request.instructions})
    assert "无需预先抠图" in prompt and "Logo" in prompt
    assert "不得改变轮廓" in prompt and "替换为花园背景" in prompt


def test_seedream_400_preserves_safe_error_details(tmp_path):
    receipts = []
    response = {
        "error": {
            "code": "InvalidParameter",
            "message": "sequential_image_generation is not supported: test-ark signed-url-secret",
        }
    }
    provider = DomesticProvider(
        settings(tmp_path),
        transport=httpx.MockTransport(lambda req: httpx.Response(400, json=response)),
    )
    with pytest.raises(ProviderError) as caught:
        provider.render([], "x", "1:1", receipts.append)
    assert "InvalidParameter" in str(caught.value)
    assert "sequential_image_generation" in str(caught.value)
    assert "test-ark" not in str(caught.value) and "secret" not in str(caught.value)
    assert receipts[-1]["invalid_parameter"] == "sequential_image_generation"


def test_seedream_pro_reference_limit_prevents_dispatch(tmp_path):
    def unexpected(req):
        raise AssertionError("Request must be rejected locally")

    provider = DomesticProvider(settings(tmp_path), transport=httpx.MockTransport(unexpected))
    with pytest.raises(ProviderError, match="10"):
        provider.render([png()] * 11, "x", "1:1", lambda r: None)


@pytest.mark.parametrize(
    "code,expected",
    [
        ("SetLimitExceeded", "安心体验模式"),
        ("QuotaExceeded", "配额不足"),
        ("ModelAccountIpmRateLimitExceeded", "调用频率"),
        ("RateLimitExceeded.EndpointRPMExceeded", "调用频率"),
        ("ServerOverloaded", "服务繁忙"),
        ("InflightBatchsizeExceeded", "并发数限制"),
        ("unrecognized-secret", "未取得可识别"),
    ],
)
def test_429_classification_without_parameter_or_secret_leak(tmp_path, code, expected):
    calls, receipts = [], []

    def handle(req):
        calls.append(req)
        return httpx.Response(
            429,
            json={
                "error": {
                    "code": code,
                    "param": "model",
                    "message": "model test-ark signed-url-secret reached limit",
                }
            },
        )

    provider = DomesticProvider(settings(tmp_path), transport=httpx.MockTransport(handle))
    with pytest.raises(ProviderError) as caught:
        provider.render([], "x", "1:1", receipts.append)
    assert len(calls) == 1
    assert expected in str(caught.value)
    assert "secret" not in str(caught.value) and "test-ark" not in str(caught.value)
    assert "涉及参数" not in str(caught.value)
    assert receipts[-1]["invalid_parameter"] is None
    assert receipts[-1]["provider_error_code"] == (None if code == "unrecognized-secret" else code)


def test_mix_scene_overrides_default_white_background():
    from studio.services.real_jobs import image_prompt

    request = Request(mode="B2", product_ids=["product"], background_id="scene")
    prompt = image_prompt(request, {"prompt": ""})
    assert "背景颜色建议 #ffffff" not in prompt
    assert "如果有，移除该主体并以自有商品替换" in prompt
    assert "如果没有" in prompt
    assert "手机状态栏" in prompt
    assert "不得退回白底棚拍" in prompt
    no_scene = image_prompt(Request(mode="B2", product_ids=["product"]), {"prompt": ""})
    assert "背景颜色建议" in no_scene
