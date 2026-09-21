import io
import json
import secrets
import zipfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi import Request as WebRequest
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from PIL import Image, ImageDraw
from pydantic import Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from studio.config import data_dir
from studio.domain.canvas import CANVAS_SIZES
from studio.domain.models import (
    FIXTURE_WARNING,
    RECIPE_FIELDS,
    Analysis,
    Evaluation,
    Recipe,
    Request,
    StrictModel,
)
from studio.providers.fixture import stamp
from studio.repositories.db import (
    analyses,
    assets,
    candidates,
    engine_for,
    evaluations,
    jobs,
    recipes,
)
from studio.services.batch import preview_remaining, submit_remaining
from studio.services.workflow import Workflow
from studio.storage.backend import StorageError
from studio.storage.images import MAX_BYTES
from studio.web.copy import COPY


class EditBody(StrictModel):
    data: dict
    version: int = Field(ge=1)


class FavoriteBody(StrictModel):
    favorite: bool


def create_app(root=None):
    root = root or data_dir()
    workflow = Workflow(engine_for(root), root)
    app = FastAPI(title=COPY["title"], docs_url=None, redoc_url=None, openapi_url=None)
    app.state.workflow = workflow
    web = Path(__file__).parent
    app.mount("/static", StaticFiles(directory=web / "static"), name="static")
    templates = Jinja2Templates(directory=web / "templates")

    @app.middleware("http")
    async def local_security(request: WebRequest, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin", "")
            if origin != str(request.base_url).rstrip("/"):
                return JSONResponse({"detail": "拒绝非同源请求"}, status_code=403)
            cookie, token = (
                request.cookies.get("studio_csrf", ""),
                request.headers.get("x-csrf-token", ""),
            )
            if not cookie or not secrets.compare_digest(cookie, token):
                return JSONResponse(
                    {"detail": "缺少或无效的 CSRF token，请刷新页面"}, status_code=403
                )
            total = 0
            chunks = []
            async for chunk in request.stream():
                total += len(chunk)
                if total > MAX_BYTES + 65536:
                    return JSONResponse({"detail": "请求超过大小上限"}, status_code=413)
                chunks.append(chunk)
            request._body = b"".join(chunks)
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' blob:; script-src 'self'; style-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]"])

    @app.exception_handler(ValueError)
    async def bad_input(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(StorageError)
    async def storage_error(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=503)

    @app.get("/")
    def home(request: WebRequest):
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"copy": COPY, "recipe_fields": RECIPE_FIELDS, "canvas_ratios": CANVAS_SIZES},
        )

    @app.get("/api/session")
    def session(request: WebRequest):
        token = request.cookies.get("studio_csrf") or secrets.token_urlsafe(32)
        response = JSONResponse({"csrf": token, "copy": COPY, "recipe_fields": RECIPE_FIELDS})
        response.set_cookie("studio_csrf", token, httponly=True, samesite="strict")
        return response

    @app.get("/api/state")
    def state():
        return {
            name: (
                [a for a in workflow.list(table, 10000) if not a.get("hidden")]
                if name == "assets"
                else workflow.list(table)
            )
            for name, table in [
                ("assets", assets),
                ("jobs", jobs),
                ("analyses", analyses),
                ("recipes", recipes),
                ("candidates", candidates),
                ("evaluations", evaluations),
            ]
        }

    @app.post("/api/assets")
    async def upload(
        file: UploadFile = File(), source: str = Form(""), fixture: bool = Form(False)
    ):
        content = await file.read(MAX_BYTES + 1)
        return workflow.upload(content, file.content_type, source, fixture)

    @app.delete("/api/assets/{asset_id}")
    def hide_asset(asset_id: str):
        workflow.store.update(assets, asset_id, {"hidden": True})
        return {"deleted": True, "note": "已从素材库删除，历史任务引用仍保留"}

    @app.post("/api/candidates/{candidate_id}/check-preview")
    def check_preview(candidate_id: str):
        from studio.services.quality import check_request

        return workflow.preview(check_request(workflow, candidate_id))

    @app.post("/api/batch/{candidate_id}/preview")
    def batch_preview(candidate_id: str):
        return preview_remaining(workflow, candidate_id)

    @app.post("/api/batch/{candidate_id}/submit")
    def batch_submit(candidate_id: str, request: WebRequest):
        return submit_remaining(
            workflow, candidate_id, request.headers.get("x-external-confirmation", "")
        )

    @app.post("/api/candidates/{candidate_id}/cutout")
    def cutout(candidate_id: str):
        candidate = workflow.get(candidates, candidate_id)
        return workflow.submit(
            Request(mode="CUTOUT", product_ids=[candidate["asset_id"]]), "cutout-" + candidate_id
        )

    @app.get("/api/assets/{asset_id}")
    def asset(asset_id: str, download: bool = False):
        try:
            item = workflow.get(assets, asset_id)
            content = workflow.storage.read_asset(item)
        except StorageError:
            raise
        except FileNotFoundError as exc:
            raise HTTPException(404, "资源不存在") from exc
        except ValueError as exc:
            raise HTTPException(404, "资源不存在") from exc
        filename = f"{'FIXTURE-' if item['fixture'] else ''}{asset_id}.png" if download else None
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'} if filename else {}
        return Response(content, media_type="image/png", headers=headers)

    @app.post("/api/jobs")
    def submit(payload: Request, request: WebRequest):
        return workflow.submit(
            payload,
            request.headers.get("idempotency-key", ""),
            request.headers.get("x-external-confirmation", ""),
        )

    @app.post("/api/jobs/preview")
    def preview(payload: Request):
        return workflow.preview(payload)

    @app.get("/api/jobs/{job_id}")
    def detail(job_id: str):
        return workflow.detail(job_id)

    @app.put("/api/analysis/{resource_id}")
    def edit_analysis(resource_id: str, body: EditBody):
        Analysis.model_validate(body.data)
        return workflow.edit("analysis", resource_id, body.data, body.version)

    @app.put("/api/recipe/{resource_id}")
    def edit_recipe(resource_id: str, body: EditBody):
        Recipe.model_validate(body.data)
        return workflow.edit("recipe", resource_id, body.data, body.version)

    @app.post("/api/candidates/{candidate_id}/evaluations")
    def evaluate(candidate_id: str, evaluation: Evaluation):
        return workflow.evaluate(candidate_id, evaluation)

    @app.put("/api/candidates/{candidate_id}/favorite")
    def favorite(candidate_id: str, body: FavoriteBody):
        return workflow.favorite(candidate_id, body.favorite)

    @app.get("/api/jobs/{job_id}/export")
    def export(job_id: str):
        detail = workflow.detail(job_id)
        if detail["job"]["state"] != "succeeded":
            raise HTTPException(409, "任务尚未完成，不能导出")
        candidate = detail["candidate"]
        fixture = detail["job"]["payload"]["fixture"]
        local = detail["job"]["payload"]["request"]["mode"] == "CUTOUT"
        prefix = "LOCAL" if local else "FIXTURE" if fixture else "MODEL"
        notice = (
            "本地自动抠图，无外发；需核查分割边缘。"
            if local
            else FIXTURE_WARNING
            if fixture
            else "真实模型输出，需人工核验；费用以供应商账单为准。"
        )
        manifest = {"notice": notice, "result": detail, "evaluations": []}
        if candidate:
            manifest["evaluations"] = [
                e for e in workflow.list(evaluations, 10000) if e["candidate_id"] == candidate["id"]
            ]
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                f"{prefix}-manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2)
            )
            if candidate:
                item = workflow.get(assets, candidate["asset_id"])
                archive.writestr(f"{prefix}-result.png", workflow.storage.read_asset(item))
                archive.writestr("READ-ME.txt", notice + "\n" + candidate["data"]["warning"])
        return Response(
            stream.getvalue(),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{prefix}-{job_id}.zip"'},
        )

    @app.post("/api/demo")
    def demo():
        # Drawn locally: these are test assets, never real model or merchant content.
        product = Image.new("RGBA", (600, 700), (0, 0, 0, 0))
        draw = ImageDraw.Draw(product)
        draw.polygon(
            [
                (200, 120),
                (100, 180),
                (155, 295),
                (220, 255),
                (220, 560),
                (420, 560),
                (420, 255),
                (485, 295),
                (535, 180),
                (425, 120),
                (360, 150),
                (265, 150),
            ],
            fill="#365d52",
            outline="#193c32",
            width=5,
        )
        draw.line((320, 153, 320, 556), fill="#bdc6b8", width=3)
        for y in range(210, 540, 65):
            draw.ellipse((329, y, 338, y + 9), fill="#eee6d5")
        back = product.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        reference = workflow.provider.render("C1", (768, 768), "#e3d8c4", "本地绘制的参考测试图")
        product_id = workflow.store_image(product, "本地程序绘制的透明服装测试夹具", True)["id"]
        back_id = workflow.store_image(back, "本地测试夹具；并非真实背面", True)["id"]
        reference_id = workflow.store_image(stamp(reference), "本地绘制的参考场景测试夹具", True)[
            "id"
        ]
        return {"product_id": product_id, "back_id": back_id, "reference_id": reference_id}

    return app


app = create_app()
