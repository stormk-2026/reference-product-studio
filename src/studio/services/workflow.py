from pathlib import Path

from PIL import Image

from studio.config import load_settings
from studio.domain.models import Analysis, Evaluation, Recipe, Request
from studio.domain.rules import compile_recipe, require_capabilities
from studio.providers.fixture import FixtureProvider
from studio.repositories.db import (
    analyses,
    assets,
    candidates,
    evaluations,
    identifier,
    jobs,
    now,
    recipes,
)
from studio.repositories.store import Store
from studio.services.external import ApprovalSigner, external_plan
from studio.storage.images import decode, safe_path, save_image


class Workflow:
    def __init__(self, engine, root: Path, *, settings=None):
        self.engine, self.root = engine, root
        self.store = Store(engine)
        self.provider = FixtureProvider()
        self.settings = settings or load_settings()
        self.approvals = ApprovalSigner()

    def get(self, table, resource_id):
        return self.store.get(table, resource_id)

    def list(self, table, limit=100):
        return self.store.list(table, limit)

    def upload(self, data, mime, source, fixture=False):
        if len(source) > 1000:
            raise ValueError("图片备注不能超过1000字")
        return self.store_image(decode(data, mime), source.strip() or "未备注图片", fixture)

    def store_image(self, image, source, fixture):
        item = save_image(self.root, image, source, fixture)
        return self.store.insert(assets, item)

    def image(self, asset_id):
        item = self.get(assets, asset_id)
        with Image.open(safe_path(self.root, item["path"])) as image:
            return image.convert("RGBA")

    def prepare(self, request: Request):
        require_capabilities(
            request.mode, self.provider.capabilities, bool(request.mask_id), request.strategy
        )
        ids = list(
            dict.fromkeys(
                request.product_ids
                + request.product_view_ids
                + [
                    x
                    for x in [
                        request.reference_id,
                        request.back_id,
                        request.mask_id,
                        request.background_id,
                        request.subject_id,
                    ]
                    if x
                ]
            )
        )
        for asset_id in ids:
            self.get(assets, asset_id)
        if request.mode in {"C_analyze", "C1"} or (
            request.mode == "C2" and request.strategy == "reference_recipe"
        ):
            if not request.reference_id:
                raise ValueError("此路线需要参考图")
        if (
            request.mode not in {"A", "A_front", "A_back", "A_pattern", "A_white", "A_views"}
            and len(request.product_ids) != 1
        ):
            raise ValueError("此路线每次仅使用一张商品图")
        if request.mask_id and request.mode not in {"B1", "B2"}:
            raise ValueError("此模式不使用蒙版，请清空蒙版选择")
        if request.mode == "B1":
            image = self.image(request.product_ids[0])
            if request.mask_id:
                mask = self.image(request.mask_id)
                if mask.size != image.size:
                    raise ValueError("蒙版必须与商品图像素尺寸一致")
                if mask.convert("L").getextrema()[1] == 0:
                    raise ValueError("蒙版不能全黑")
            elif image.getchannel("A").getextrema()[0] == 255:
                raise ValueError("需要透明商品图或蒙版；当前不支持自动抠图")
            if image.getchannel("A").getextrema()[1] == 0:
                raise ValueError("商品图完全透明")
        if request.mode == "B2":
            if not request.change_background and not request.change_subject:
                raise ValueError("请选择换背景或换主体")
            if request.change_subject and not request.subject_id:
                raise ValueError("换主体需要上传并选择自己的商品图")
        if request.product_view_ids:
            if request.mode != "B2" or request.change_subject or request.batch_product_ids:
                raise ValueError("多角度仅用于同一商品混图，不能同时批量或替换主体")
            combined = request.product_ids + request.product_view_ids
            if len(combined) != len(set(combined)):
                raise ValueError("商品多角度图片不能重复")
        if request.mode == "CUTOUT" and request.execution != "fixture":
            raise ValueError("抠图只在本地执行，不使用外部模型")
        if request.batch_product_ids:
            if request.mode != "B2" or len(set(request.batch_product_ids)) != len(
                request.batch_product_ids
            ):
                raise ValueError("批量仅用于一键混图且图片不能重复")
            if request.batch_index >= len(request.batch_product_ids) or request.product_ids != [
                request.batch_product_ids[request.batch_index]
            ]:
                raise ValueError("批量图片顺序不匹配")
            for item in request.batch_product_ids:
                self.get(assets, item)
            if request.batch_index and not request.anchor_candidate_id:
                raise ValueError("先通过首张，再生成剩余图片")
        anchor_asset_id = None
        if request.anchor_candidate_id:
            anchor = self.get(candidates, request.anchor_candidate_id)
            anchor_job = self.get(jobs, anchor["job_id"])
            original = Request.model_validate(anchor_job["payload"]["request"])
            if (
                anchor_job["state"] != "succeeded"
                or original.mode != "B2"
                or original.batch_index != 0
                or original.batch_product_ids != request.batch_product_ids
                or not request.batch_product_ids
            ):
                raise ValueError("风格锚点必须是此批次已完成的首张候选")
            if request.execution == "real" and anchor["fixture"]:
                raise ValueError("真实批量不能使用测试候选作为确认图")
            anchor_asset_id = anchor["asset_id"]
            ids.append(anchor_asset_id)
        analysis_snapshot = (
            self.get(analyses, request.analysis_id)["data"] if request.analysis_id else None
        )
        recipe_snapshot = (
            self.get(recipes, request.recipe_id)["data"] if request.recipe_id else None
        )
        if request.mode == "C2" and recipe_snapshot is None:
            raise ValueError("请先解析参考图并选择配方")
        if request.analysis_id:
            linked = self.get(analyses, request.analysis_id)
            if linked["input_ids"] != request.product_ids:
                raise ValueError("分析与当前商品不匹配，请重新分析或清空分析选择")
        prompt = request.instructions
        if request.preserve:
            prompt += "\n本次请求必须保留：" + request.preserve
        if request.mode == "C2":
            prompt += "\n" + compile_recipe(Recipe.model_validate(recipe_snapshot))
        payload = dict(
            request=request.model_dump(),
            anchor_asset_id=anchor_asset_id,
            analysis=analysis_snapshot,
            recipe=recipe_snapshot,
            prompt=prompt,
            provider="fixture",
            model=self.provider.model,
            template_version="studio-v1",
            fixture=True,
            input_ids=ids,
            recipient="本地 Fixture，不外发",
            sent_asset_ids=[],
            external_authorized=False,
        )
        if request.execution == "real":
            plan = external_plan(request, self.settings)
            if anchor_asset_id:
                plan["sent_asset_ids"] = list(
                    dict.fromkeys(plan["sent_asset_ids"] + [anchor_asset_id])
                )
            if plan["provider"] == "volcengine" and len(plan["sent_asset_ids"]) > 10:
                raise ValueError("Seedream 5.0 Pro 最多 10 张参考图，包含商品、背景和风格样张")
            sent = [self.get(assets, asset_id) for asset_id in plan["sent_asset_ids"]]
            if sum(asset["bytes"] for asset in sent) > 24 * 1024 * 1024:
                raise ValueError("外发图片合计超过24MB，请减少或缩小图片")
            if request.mode == "C2" and request.recipe_id:
                if self.get(recipes, request.recipe_id)["fixture"]:
                    raise ValueError("真实 C2 需要真实分析产生的配方；测试配方不能冒充真实参考解析")
            payload.update(
                **plan,
                fixture=False,
                template_version="domestic-v2-simple-flow",
                input_fixture=any(self.get(assets, asset_id)["fixture"] for asset_id in ids),
                sent_assets=[
                    {
                        key: asset[key]
                        for key in ["id", "sha256", "source", "width", "height", "fixture"]
                    }
                    for asset in sent
                ],
            )
        return payload

    def preview(self, request: Request):
        if request.execution != "real":
            raise ValueError("只有真实请求需要外发预览")
        payload = self.prepare(request)
        from studio.services.real_jobs import image_prompt

        return {
            "plan": payload,
            "compiled_prompt": (
                image_prompt(request, payload)
                if request.mode not in {"A", "C_analyze"}
                else None
            ),
            "sent_assets": payload["sent_assets"],
            "confirmation_token": self.approvals.issue(payload),
        }

    def submit(self, request: Request, key: str, confirmation_token: str = ""):
        if not key or len(key) > 128:
            raise ValueError("无效的幂等键")
        payload = self.prepare(request)
        if request.execution == "real":
            key = self.approvals.verify(confirmation_token, payload)
            payload["external_authorized"] = True
        return self.store.enqueue(key, payload)

    def detail(self, job_id):
        result = {
            "job": self.get(jobs, job_id),
            "analysis": None,
            "recipe": None,
            "candidate": None,
        }
        for name, table in [("analysis", analyses), ("recipe", recipes), ("candidate", candidates)]:
            result[name] = self.store.for_job(table, job_id)
        return result

    def edit(self, kind, resource_id, data, version):
        table, schema = (analyses, Analysis) if kind == "analysis" else (recipes, Recipe)
        value = schema.model_validate(data).model_dump()
        if kind == "recipe":
            compile_recipe(Recipe.model_validate(value))
        return self.store.revise(table, resource_id, value, version)

    def evaluate(self, candidate_id, evaluation: Evaluation):
        self.get(candidates, candidate_id)
        item = dict(
            id=identifier(),
            candidate_id=candidate_id,
            data=evaluation.model_dump(),
            created_at=now(),
        )
        return self.store.insert(evaluations, item)

    def favorite(self, candidate_id, value: bool):
        return self.store.update(candidates, candidate_id, {"favorite": value})
