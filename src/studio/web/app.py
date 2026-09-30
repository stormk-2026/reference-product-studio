import io
import json
import os
import secrets
import zipfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi import Request as WebRequest
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from PIL import Image, ImageDraw
from pydantic import Field
from starlette.concurrency import run_in_threadpool
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
from studio.repositories.store import QuotaError
from studio.services.accounts import Accounts, AuthError, RateLimitError
from studio.services.batch import preview_remaining, submit_remaining
from studio.services.content_batch import preview_series, series_status, submit_series
from studio.services.email_registration import EmailRegistration, MailUnavailable, SMTPMailer
from studio.services.tenants import Tenants, WorkflowProxy, current_workflow
from studio.services.workflow import Workflow
from studio.storage.backend import StorageError
from studio.storage.images import MAX_BYTES
from studio.web.copy import COPY


class EditBody(StrictModel):
    data: dict
    version: int = Field(ge=1)


class FavoriteBody(StrictModel):
    favorite: bool


class Credentials(StrictModel):
    username: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=10, max_length=128)


class EmailBody(StrictModel):
    email: str = Field(min_length=3, max_length=254)


class EmailSignup(EmailBody):
    password: str = Field(min_length=10, max_length=128)
    challenge_id: str = Field(pattern=r"^[A-Za-z0-9_-]{32}$")
    code: str = Field(pattern=r"^[0-9]{6}$")


def create_app(root=None, *, auth_enabled=None, mailer=None, registration_enabled=None):
    root = root or data_dir()
    auth_enabled = (
        (os.environ.get("STUDIO_AUTH_ENABLED") == "1") if auth_enabled is None else auth_enabled
    )
    accounts = Accounts(root) if auth_enabled else None
    tenants = Tenants(accounts) if accounts else None
    workflow = WorkflowProxy() if auth_enabled else Workflow(engine_for(root), root)
    app = FastAPI(title=COPY["title"], docs_url=None, redoc_url=None, openapi_url=None)
    app.state.workflow = workflow
    app.state.accounts = accounts
    registration = (
        EmailRegistration(
            accounts,
            mailer or SMTPMailer(),
            os.environ.get("STUDIO_REGISTRATION_ENABLED") == "1"
            if registration_enabled is None
            else registration_enabled,
        )
        if accounts
        else None
    )
    app.state.registration = registration

    def request_peer(request):
        peer = request.client.host if request.client else "unknown"
        return (
            request.headers.get("x-real-ip", peer)
            if os.environ.get("STUDIO_TRUST_PROXY") == "1"
            else peer
        )

    app.state.tenants = tenants
    web = Path(__file__).parent
    app.mount("/static", StaticFiles(directory=web / "static"), name="static")
    templates = Jinja2Templates(directory=web / "templates")

    @app.middleware("http")
    async def local_security(request: WebRequest, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin", "")
            host = request.headers.get("host", "").split(":", 1)[0].lower()
            expected_origin = (
                "https://stormstudio.top"
                if host == "stormstudio.top"
                else str(request.base_url).rstrip("/")
            )
            if origin != expected_origin:
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
                if total > (
                    8192 if request.url.path.startswith("/api/auth/") else MAX_BYTES + 65536
                ):
                    return JSONResponse({"detail": "请求超过大小上限"}, status_code=413)
                chunks.append(chunk)
            request._body = b"".join(chunks)
        context_token = None
        if accounts:
            user = await run_in_threadpool(
                accounts.resolve, request.cookies.get("studio_session", "")
            )
            request.state.user = user
            public = request.url.path in {
                "/login",
                "/api/session",
                "/api/auth/login",
                "/api/auth/register",
                "/api/auth/send-code",
                "/api/auth/options",
            } or request.url.path.startswith("/static/")
            if not public and not user:
                return (
                    RedirectResponse("/login", status_code=303)
                    if request.url.path == "/"
                    else JSONResponse({"detail": "请先登录"}, status_code=401)
                )
            if user:
                selected = await run_in_threadpool(tenants.workflow, user)
                context_token = current_workflow.set(selected)
            try:
                if request.method == "POST" and request.url.path.startswith("/api/auth/"):
                    peer = request_peer(request)
                    if request.url.path == "/api/auth/login":
                        await run_in_threadpool(
                            accounts.throttle_many,
                            [("login:" + peer, 15, 900), ("login-global", 100, 900)],
                        )
                if user and request.method == "POST":
                    path = request.url.path
                    if path == "/api/jobs" or path.endswith(("/submit", "/cutout")):
                        await run_in_threadpool(
                            accounts.throttle, "generation:" + user["id"], 4, 60
                        )
                    elif path == "/api/assets":
                        await run_in_threadpool(accounts.throttle, "upload:" + user["id"], 15, 60)
            except RateLimitError as exc:
                if context_token is not None:
                    current_workflow.reset(context_token)
                return JSONResponse(
                    {"detail": str(exc)}, status_code=429, headers={"Retry-After": "60"}
                )
        try:
            response = await call_next(request)
        finally:
            if context_token is not None:
                current_workflow.reset(context_token)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' blob:; script-src 'self'; style-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "stormstudio.top"]
    )

    @app.exception_handler(QuotaError)
    async def quota_error(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=403)

    @app.exception_handler(RateLimitError)
    async def rate_limit_error(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=429, headers={"Retry-After": "60"})

    @app.exception_handler(MailUnavailable)
    async def mail_unavailable(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=503)

    @app.exception_handler(AuthError)
    async def auth_error(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(ValueError)
    async def bad_input(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(StorageError)
    async def storage_error(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=503)

    @app.get("/login")
    def login_page(request: WebRequest):
        if not accounts or request.state.user:
            return RedirectResponse("/", status_code=303)
        return templates.TemplateResponse(request=request, name="login.html", context={})

    def logged_in(user, request):
        response = JSONResponse({"username": user["username"], "owner": bool(user["owner"])})
        response.set_cookie(
            "studio_session",
            accounts.issue(user),
            max_age=7 * 86400,
            httponly=True,
            samesite="lax",
            secure=request.url.hostname == "stormstudio.top",
        )
        # Login rotates any anonymous or previous authenticated session.
        accounts.logout(request.cookies.get("studio_session", ""))
        return response

    @app.get("/api/auth/options")
    def auth_options():
        return {
            "email_registration": bool(registration and registration.enabled),
            "message": "验证邮箱后可注册"
            if registration and registration.enabled
            else "邮箱注册暂未开放；已有主账户可正常登录",
        }

    @app.post("/api/auth/send-code")
    def send_code(body: EmailBody, request: WebRequest):
        if not registration:
            raise HTTPException(404)
        challenge = registration.send_code(body.email, request_peer(request))
        return {
            "challenge_id": challenge,
            "retry_after": 60,
            "message": "如果该邮箱可注册，验证码已发送；请检查收件箱或垃圾邮件。",
        }

    @app.post("/api/auth/register")
    def register(body: EmailSignup, request: WebRequest):
        if not registration:
            raise HTTPException(404)
        user = registration.register(
            body.email, body.password, body.challenge_id, body.code, request_peer(request)
        )
        tenants.workflow(user)
        return logged_in(user, request)

    @app.post("/api/auth/login")
    def login(body: Credentials, request: WebRequest):
        if not accounts:
            raise HTTPException(404)
        accounts.throttle("username:" + body.username.lower().strip(), 30, 900)
        return logged_in(accounts.login(body.username, body.password), request)

    @app.post("/api/auth/logout")
    def logout(request: WebRequest):
        if accounts:
            accounts.logout(request.cookies.get("studio_session", ""))
        response = JSONResponse({"ok": True})
        response.delete_cookie("studio_session")
        return response

    @app.get("/api/account")
    def account(request: WebRequest):
        if not accounts:
            return {"enabled": False}
        user = request.state.user
        return {
            "enabled": True,
            "username": user["username"],
            "owner": bool(user["owner"]),
            "quota": workflow.store.quota(),
        }

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
        response = JSONResponse(
            {
                "csrf": token,
                "copy": COPY,
                "recipe_fields": RECIPE_FIELDS,
                "auth_enabled": auth_enabled,
                "authenticated": bool(getattr(request.state, "user", None)),
            }
        )
        response.set_cookie(
            "studio_csrf",
            token,
            httponly=True,
            samesite="strict",
            secure=request.headers.get("host", "").split(":", 1)[0].lower() == "stormstudio.top",
        )
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
        if accounts and current_workflow.get().store.quota_limit is not None:
            if fixture:
                raise HTTPException(403, "不支持上传测试素材")
            existing = workflow.list(assets, 10000)
            if len(existing) >= 100 or sum(a["bytes"] for a in existing) >= 100 * 1024 * 1024:
                raise HTTPException(403, "体验账号最多保存 100 张图片或 100 MB 素材")
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

    @app.post("/api/content/series/{candidate_id}/preview")
    def content_series_preview(candidate_id: str):
        return preview_series(workflow, candidate_id)

    @app.post("/api/content/series/{candidate_id}/submit")
    def content_series_submit(candidate_id: str, request: WebRequest):
        return submit_series(
            workflow, candidate_id, request.headers.get("x-external-confirmation", "")
        )

    @app.get("/api/content/series/{candidate_id}")
    def content_series_status(candidate_id: str):
        return series_status(workflow, candidate_id)

    @app.get("/api/content/series/{candidate_id}/export")
    def content_series_export(candidate_id: str):
        status = series_status(workflow, candidate_id)
        if not status["complete"]:
            raise HTTPException(409, "套图尚未全部完成")
        first = workflow.get(candidates, candidate_id)
        deck = first["data"]["deck"]
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
            for index, aid in enumerate(
                [status["first_asset_id"]] + [t["asset_id"] for t in status["tasks"]]
            ):
                archive.writestr(
                    f"page-{index + 1:02d}.png",
                    workflow.storage.read_asset(workflow.get(assets, aid)),
                )
            archive.writestr("发布正文.txt", deck["post_title"] + "\n\n" + deck["post_body"])
            archive.writestr(
                "核对说明.txt", "模型生成视觉背景，原始商品或截图及文字由程序叠放；发布前人工核对。"
            )
        return Response(
            stream.getvalue(),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="CONTENT-{candidate_id}.zip"'},
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
        content_layout = detail["job"]["payload"]["request"]["mode"] == "CONTENT_RENDER"
        prefix = (
            "CONTENT" if content_layout else "LOCAL" if local else "FIXTURE" if fixture else "MODEL"
        )
        notice = (
            "本地自动抠图，无外发；需核查分割边缘。"
            if local
            else FIXTURE_WARNING
            if fixture
            else "真实模型输出，需人工核验；费用以供应商账单为准。"
        )
        if content_layout:
            notice = "本地宣传排版；文案需人工核对。" + (FIXTURE_WARNING if fixture else "")
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
            if candidate and content_layout:
                for index, aid in enumerate(candidate["data"]["pages"]):
                    archive.writestr(
                        f"page-{index + 1:02d}.png",
                        workflow.storage.read_asset(workflow.get(assets, aid)),
                    )
                deck = candidate["data"]["deck"]
                archive.writestr("发布正文.txt", deck["post_title"] + "\n\n" + deck["post_body"])
                archive.writestr(
                    "核对说明.txt", deck["review_notes"] + "\n" + candidate["data"]["warning"]
                )
            elif candidate:
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
        if accounts:
            raise HTTPException(404)
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
