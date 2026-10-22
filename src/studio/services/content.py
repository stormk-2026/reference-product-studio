"""Truth-bounded copy and signed one-call visual pages."""

import hashlib
import json
import time

from studio.domain.content import ContentDeck, ContentPage
from studio.domain.models import Request
from studio.providers.domestic import DomesticProvider, ProviderError
from studio.repositories.db import analyses, assets, candidates, identifier, jobs, now
from studio.services.external import external_plan


def prepare_content(workflow, request):
    brief = request.content_brief
    if (
        not brief
        or len(request.product_ids) > 6
        or len(set(request.product_ids)) != len(request.product_ids)
    ):
        raise ValueError("请填写名称、真实卖点，并选择 1–6 张不重复的截图或商品图")
    if any(
        (
            request.background_id,
            request.subject_id,
            request.reference_id,
            request.back_id,
            request.mask_id,
            request.product_view_ids,
            request.batch_product_ids,
            request.analysis_id,
            request.recipe_id,
            request.check_candidate_id,
            request.instructions,
            request.preserve,
        )
    ):
        raise ValueError("宣传图文只接受本工具的素材与文案，不能混用场景或历史分析参数")
    if request.ratio != "3:4":
        raise ValueError("宣传图文首版使用 3:4 画布（1152×1536）")
    items = [workflow.get(assets, aid) for aid in request.product_ids]
    anchor_asset_id = None
    if request.mode == "CONTENT_SCENE":
        if request.execution != "real" or not request.content_deck:
            raise ValueError("Seedream 视觉图需要已确认文案和真实模型模式")
        validate_deck(request.content_deck, brief, len(items))
        from studio.services.content_render import preflight_scene_deck

        preflight_scene_deck(request.content_deck)
        if request.content_page_index >= brief.page_count:
            raise ValueError("页面序号超出本次套图")
        if request.content_page_index == 0 and request.anchor_candidate_id:
            raise ValueError("首页不能引用历史样张")
        if request.content_page_index > 0:
            if not request.anchor_candidate_id:
                raise ValueError("请先生成并确认首页，再制作余下页面")
            anchor = workflow.get(candidates, request.anchor_candidate_id)
            anchor_job = workflow.get(jobs, anchor["job_id"])
            first = Request.model_validate(anchor_job["payload"]["request"])
            if (
                anchor_job["state"] != "succeeded"
                or anchor["fixture"]
                or first.mode != "CONTENT_SCENE"
                or first.content_page_index != 0
                or first.product_ids != request.product_ids
                or first.content_brief != brief
                or first.content_deck != request.content_deck
            ):
                raise ValueError("风格样张与当前图片、文案或方案不一致，请重新预览首页")
            anchor_asset_id = anchor["data"]["background_asset_id"]
    elif request.anchor_candidate_id or request.content_page_index:
        raise ValueError("风格样张和页面序号只用于 Seedream 视觉图")
    if request.mode == "CONTENT_RENDER":
        if request.execution != "fixture":
            raise ValueError("宣传排版在本地执行，不调用生图模型")
        if not request.content_deck:
            raise ValueError("请先确认逐页文案")
        validate_deck(request.content_deck, brief, len(items))
    elif request.mode == "CONTENT_POLISH":
        if request.execution != "real" or not request.content_deck:
            raise ValueError("Kimi 润色需要已有文案并使用真实模型")
        validate_deck(request.content_deck, brief, len(items))
    elif request.mode == "CONTENT_COPY" and request.content_deck:
        raise ValueError("起草文案时不接受已排版内容")
    if request.content_polish_note and request.mode != "CONTENT_POLISH":
        raise ValueError("润色意见只用于 Kimi 文案润色")
    prompt = (
        "为下列资料生成宣传图文，只使用提供的事实。图片不得被重绘。\n"
        + (
            "App 截图方案：封面介绍价值，正文讲可见功能、操作流程和适用人群。\n"
            if brief.kind == "app"
            else "商品种草方案：封面展示商品，正文讲已知卖点、外观细节和使用场景。\n"
        )
        + json.dumps(brief.model_dump(), ensure_ascii=False)
        + f"\n必须输出 {brief.page_count} 页；本次共 {len(items)} 张图片，序号 0–{len(items) - 1}。"
    )
    if request.mode == "CONTENT_POLISH":
        prompt = (
            "仅润色以下已确认文案的表达，不新增事实、数字、体验、承诺或功效；"
            "保持页数、每页 image_index、内容重点与素材关联。输出完整 ContentDeck JSON。"
            "若原文有未经证实的断言，改成谨慎表达并写在 review_notes。\n"
            + json.dumps(
                {
                    "brief": brief.model_dump(),
                    "original_deck": request.content_deck.model_dump(),
                    "style_note": request.content_polish_note,
                },
                ensure_ascii=False,
            )
        )
    if request.mode == "CONTENT_SCENE":
        page = request.content_deck.pages[request.content_page_index]
        style = {
            "clean": "清爽明亮的蓝白科技感",
            "bold": "高对比深色商业视觉",
            "warm": "温暖奶油色生活方式视觉",
        }[brief.style]
        prompt = (
            "生成一张高品质3:4竖版商业宣传海报的纯视觉背景图层。"
            "仅生成抽象图形、空间、真实光影、材质、层次和与主题相关的环境氛围；"
            "中间大面积预留干净空间，供后续程序放入真实素材。上方和下方也留有可读文字的安全空间。"
            "禁止生成任何文字、字母、数字、Logo、水印之外的标志、手机界面、App截图、商品主体、假按钮或价格标签。"
            "视觉应有明确焦点、丰富但克制的光影，不要纯色白图，不要简单渐变。"
            "后续会由程序叠放用户原始截图或商品照片及真实文案，请不要在背景中自行绘制它们。"
            f"方案：{'App 产品展示' if brief.kind == 'app' else '实物商品种草'}；"
            f"品牌主题：{brief.name}；本页主题：{page.title}；风格：{style}；强调色：{brief.accent}。"
            "用户提供的事实仅作为氛围参考，不在画面上写出来：" + brief.facts[:500]
        )
    fixture = (
        request.execution == "fixture"
        if request.mode == "CONTENT_COPY"
        else any(i["fixture"] for i in items)
    )
    payload = dict(
        request=request.model_dump(),
        prompt=prompt,
        provider="local-layout",
        model="carousel-v1",
        template_version="carousel-v1",
        fixture=fixture,
        input_ids=request.product_ids + ([anchor_asset_id] if anchor_asset_id else []),
        sent_asset_ids=[],
        external_authorized=False,
        recipient="本地排版，不外发",
        analysis=None,
        recipe=None,
    )
    if request.execution == "real":
        sent = (
            items
            if request.mode == "CONTENT_COPY"
            else [workflow.get(assets, anchor_asset_id)]
            if anchor_asset_id
            else []
        )
        if sum(i["bytes"] for i in sent) > 24 * 1024 * 1024:
            raise ValueError("外发图片合计超过24MB，请缩小图片")
        plan = external_plan(request, workflow.settings)
        plan["sent_asset_ids"] = [i["id"] for i in sent]
        payload.update(
            **plan,
            fixture=False,
            sent_assets=[
                {k: i[k] for k in ("id", "sha256", "source", "width", "height", "fixture")}
                for i in sent
            ],
        )
    payload["anchor_asset_id"] = anchor_asset_id
    return payload


def validate_deck(deck, brief, count):
    if len(deck.pages) != brief.page_count:
        raise ValueError("文案页数与本次设置不一致，请重新检查")
    if any(page.image_index >= count for page in deck.pages):
        raise ValueError("页面引用了未选择的图片，请重新选择")


def fixture_deck(brief, count):
    labels = [
        "封面",
        "核心功能" if brief.kind == "app" else "商品卖点",
        "使用场景",
        "细节",
        "适合谁",
        "总结",
    ]
    return ContentDeck(
        pages=[
            ContentPage(
                label=labels[i],
                title=brief.name[:36] if i == 0 else labels[i],
                body="测试文案：未进行真实产品分析。",
                image_index=i % count,
            )
            for i in range(brief.page_count)
        ],
        post_title=brief.name[:40],
        post_body="测试夹具正文，不代表真实体验。",
        review_notes="仅用于离线流程验证。",
    )


def run_content(workflow, job, provider=None):
    from studio.services.content_render import render_deck

    payload = job["payload"]
    request = Request.model_validate(payload["request"])
    brief = request.content_brief
    started = time.monotonic()
    if request.mode in {"CONTENT_COPY", "CONTENT_POLISH"}:
        if request.execution == "real":
            plan = external_plan(request, workflow.settings)
            plan["sent_asset_ids"] = [a["id"] for a in payload["sent_assets"]]
            if (
                not payload.get("external_authorized")
                or payload.get("max_calls") != 1
                or any(
                    plan[k] != payload[k]
                    for k in ("provider", "model", "recipient", "sent_asset_ids")
                )
            ):
                raise ProviderError("文案任务缺少有效外发授权或接收方已变化；未外发")
            pictures = []
            for sent in payload["sent_assets"]:
                content = workflow.storage.read_asset(workflow.get(assets, sent["id"]))
                if hashlib.sha256(content).hexdigest() != sent["sha256"]:
                    raise ProviderError("素材已改变，请重新预览；未外发")
                pictures.append(content)

            def received(receipt):
                payload["receipt"] = receipt
                workflow.store.update(
                    jobs,
                    job["id"],
                    {
                        "payload": payload,
                        "phase": "received",
                        "provider_request_id": receipt.get("provider_request_id"),
                    },
                )

            workflow.store.update(jobs, job["id"], {"phase": "dispatching"})
            result = (provider or DomesticProvider(workflow.settings)).analyze(
                request.mode,
                pictures,
                request.product_ids if pictures else [],
                payload["prompt"],
                received,
            )
            deck = ContentDeck.model_validate(result.value.model_dump())
        else:
            deck = fixture_deck(brief, len(request.product_ids))
        try:
            validate_deck(deck, brief, len(request.product_ids))
            if request.mode == "CONTENT_POLISH" and [p.image_index for p in deck.pages] != [
                p.image_index for p in request.content_deck.pages
            ]:
                raise ValueError("润色更改了图片引用")
        except ValueError as exc:
            raise ProviderError(
                "返回文案页数或素材引用不符合要求；未自动重试，请检查记录后重做"
            ) from exc
        workflow.store.complete(
            job["id"],
            analyses,
            dict(
                id=identifier(),
                job_id=job["id"],
                data=deck.model_dump(),
                version=1,
                created_at=now(),
                fixture=payload["fixture"],
                input_ids=request.product_ids,
            ),
        )
        return
    if request.mode == "CONTENT_SCENE":
        from studio.services.content_render import render_scene_page

        plan = external_plan(request, workflow.settings)
        plan["sent_asset_ids"] = [a["id"] for a in payload["sent_assets"]]
        if (
            not payload.get("external_authorized")
            or payload.get("max_calls") != 1
            or any(
                plan[k] != payload[k] for k in ("provider", "model", "recipient", "sent_asset_ids")
            )
        ):
            raise ProviderError("视觉任务缺少有效外发授权或接收方已变化；未外发")
        sent_images = []
        for sent in payload["sent_assets"]:
            raw = workflow.storage.read_asset(workflow.get(assets, sent["id"]))
            if hashlib.sha256(raw).hexdigest() != sent["sha256"]:
                raise ProviderError("风格样张已改变，请重新预览；未外发")
            sent_images.append(raw)

        def received(receipt):
            payload["receipt"] = receipt
            workflow.store.update(
                jobs,
                job["id"],
                {
                    "payload": payload,
                    "phase": "received",
                    "provider_request_id": receipt.get("provider_request_id"),
                },
            )

        workflow.store.update(jobs, job["id"], {"phase": "dispatching"})
        result = (provider or DomesticProvider(workflow.settings)).render(
            sent_images, payload["prompt"], "3:4", received
        )
        background = workflow.store_image(
            result.image, "宣传图文 · Seedream 视觉图层", False, preserve_on_storage_failure=True
        )
        images = [workflow.image(aid) for aid in request.product_ids]
        final, qa = render_scene_page(
            brief, request.content_deck, images, request.content_page_index, result.image
        )
        saved = workflow.store_image(
            final, "宣传图文 · AI 视觉成图", False, preserve_on_storage_failure=True
        )
        workflow.store.complete(
            job["id"],
            candidates,
            dict(
                id=identifier(),
                job_id=job["id"],
                asset_id=saved["id"],
                created_at=now(),
                fixture=False,
                favorite=False,
                data=dict(
                    mode="CONTENT_SCENE",
                    request=request.model_dump(),
                    provider=payload["provider"],
                    model=payload["model"],
                    page_index=request.content_page_index,
                    deck=request.content_deck.model_dump(),
                    background_asset_id=background["id"],
                    layout_check=qa,
                    input_ids=payload["input_ids"],
                    sent_asset_ids=payload["sent_asset_ids"],
                    warning="Seedream 只生成视觉背景；真实素材和文字由程序叠放。需人工核对商品细节、文字与画面。",
                    transformations=["Seedream 视觉背景", "原始素材等比叠放", "中文文案本地排版"],
                    duration_seconds=time.monotonic() - started,
                ),
            ),
        )
        return
    workflow.store.update(jobs, job["id"], {"phase": "dispatching"})
    images = [workflow.image(aid) for aid in request.product_ids]
    # Layout-check every page before persisting any output. Samples and full renders use identical tokens.
    pages, qa = render_deck(brief, request.content_deck, images, fixture=payload["fixture"])
    visible = pages[:2] if request.content_sample else pages
    saved = [
        workflow.store_image(image, "宣传图文 · 本地排版", payload["fixture"]) for image in visible
    ]
    data = dict(
        mode="CONTENT_RENDER",
        request=request.model_dump(),
        provider="local-layout",
        model="carousel-v1",
        fixture=payload["fixture"],
        pages=[item["id"] for item in saved],
        deck=request.content_deck.model_dump(),
        layout_check=qa,
        sample=request.content_sample,
        input_ids=request.product_ids,
        cost_estimate=0,
        duration_seconds=time.monotonic() - started,
        warning="文字由程序排版，截图/商品图等比呈现；发布前请核对文案事实与图片清晰度。",
        transformations=["1152×1536；原始素材等比缩放，不重绘、不裁切；全套统一字号"],
        sent_asset_ids=[],
        recipient="本地排版，不外发",
    )
    workflow.store.complete(
        job["id"],
        candidates,
        dict(
            id=identifier(),
            job_id=job["id"],
            asset_id=saved[0]["id"],
            data=data,
            created_at=now(),
            fixture=payload["fixture"],
            favorite=False,
        ),
    )
