import hashlib
import hmac
import json
import secrets
import time

from studio.domain.models import Request

KIMI_BASE = "https://api.moonshot.cn/v1"
ARK_BASE = "https://ark.cn-beijing.volces.com/api/v3"
SEEDREAM_MODEL = "doubao-seedream-5-0-pro-260628"


def external_plan(request: Request, settings):
    understanding = request.mode in {"A", "C_analyze"}
    if understanding:
        if settings.moonshot_base_url.rstrip("/") != KIMI_BASE or settings.kimi_model != "kimi-k3":
            raise ValueError("本次适配器仅支持 Kimi 中国区官方地址和 kimi-k3；未静默替换配置")
        if not settings.moonshot_api_key.get_secret_value():
            raise ValueError("请在本项目 .env 填写 MOONSHOT_API_KEY")
        image_ids = (
            [request.reference_id]
            if request.mode == "C_analyze"
            else request.product_ids + ([request.back_id] if request.back_id else [])
        )
        provider, model, recipient = (
            "moonshot",
            settings.kimi_model,
            "Moonshot / Kimi 中国区（api.moonshot.cn）",
        )
    else:
        if (
            settings.ark_base_url.rstrip("/") != ARK_BASE
            or settings.seedream_model != SEEDREAM_MODEL
        ):
            raise ValueError(
                "当前仅为已配置的 Seedream 5.0 Pro 型号编译请求；请核对国内方舟地址与精确模型 ID"
            )
        if not settings.ark_api_key.get_secret_value():
            raise ValueError("请在本项目 .env 填写 ARK_API_KEY")
        if request.mask_id and request.mode != "B1":
            raise ValueError(
                "当前 Seedream 适配器未验证蒙版局部编辑能力，不能静默降级；B1 蒙版仅在本地合成"
            )
        image_ids = [] if request.mode == "B1" else list(request.product_ids)
        if request.mode == "B2":
            image_ids.extend(request.product_view_ids)
        if request.mode == "C1" or (
            request.mode == "C2" and request.strategy == "reference_recipe"
        ):
            image_ids.append(request.reference_id)
        if request.mode.startswith("A_") and request.back_id:
            image_ids.append(request.back_id)
        if request.mode == "B2" and request.change_subject and request.subject_id:
            image_ids.append(request.subject_id)
        if request.background_id and request.mode not in {"A", "C_analyze"}:
            image_ids.append(request.background_id)
        provider, model, recipient = (
            "volcengine",
            settings.seedream_model,
            "火山方舟中国区（ark.cn-beijing.volces.com）",
        )
    return dict(
        provider=provider,
        model=model,
        recipient=recipient,
        sent_asset_ids=list(dict.fromkeys(x for x in image_ids if x)),
        max_calls=1,
        max_output_images=0 if understanding else 1,
        cost_estimate=None,
        cost_basis="unknown；未验证当前账户定价。按本次调用数量授权，不承诺金额上限。",
        retries=0,
        query_supported=False,
    )


class ApprovalSigner:
    """Short-lived approval bound to the complete immutable request preview."""

    def __init__(self):
        self.key = secrets.token_bytes(32)

    def issue(self, payload):
        expires = str(int(time.time()) + 900)
        nonce = secrets.token_hex(16)
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        body = ".".join([expires, nonce, digest])
        signature = hmac.new(self.key, body.encode(), hashlib.sha256).hexdigest()
        return body + "." + signature

    def verify(self, token, payload):
        try:
            expires, nonce, digest, signature = token.split(".")
            body = ".".join([expires, nonce, digest])
            expected = hmac.new(self.key, body.encode(), hashlib.sha256).hexdigest()
            actual_digest = hashlib.sha256(
                json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
            ).hexdigest()
            if (
                int(expires) < time.time()
                or not hmac.compare_digest(signature, expected)
                or not hmac.compare_digest(digest, actual_digest)
            ):
                raise ValueError
        except (ValueError, AttributeError):
            raise ValueError("外发确认缺失、过期或输入已改变；请重新预览后授权本次调用") from None
        return "real-" + hashlib.sha256(token.encode()).hexdigest()
