"""Private OSS or local assets. Locations are immutable; no public URLs or credentials in DB."""

import hashlib
import re
from pathlib import Path

from studio.config import load_settings

MAX_STORED_BYTES = 128 * 1024 * 1024


class StorageError(ValueError):
    pass


class AssetStorage:
    def __init__(self, root: Path, settings=None):
        self.root = root
        self.settings = settings or load_settings()
        self._client = None
        if self.settings.asset_backend == "oss":
            self.validate_oss()

    def validate_oss(self):
        s = self.settings
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,61}[a-z0-9]", s.oss_bucket):
            raise StorageError("请配置有效的 STUDIO_OSS_BUCKET")
        if not re.fullmatch(r"[a-z0-9-]+", s.oss_region) or s.oss_endpoint not in {
            f"https://oss-{s.oss_region}.aliyuncs.com",
            f"https://oss-{s.oss_region}-internal.aliyuncs.com",
        }:
            raise StorageError("OSS Endpoint 必须是对应地域的阿里云 HTTPS 地址")
        if not re.fullmatch(r"(?:[a-zA-Z0-9_-]+/)+", s.oss_prefix):
            raise StorageError("OSS 目录不能为空，格式示例：storm-studio/")
        if (
            not s.oss_access_key_id.get_secret_value()
            or not s.oss_access_key_secret.get_secret_value()
        ):
            raise StorageError("请填写本项目专用 OSS 访问凭据")

    def client(self):
        self.validate_oss()
        if self._client is None:
            import alibabacloud_oss_v2 as oss

            s = self.settings
            cfg = oss.config.load_default()
            cfg.region, cfg.endpoint = s.oss_region, s.oss_endpoint
            cfg.credentials_provider = oss.credentials.StaticCredentialsProvider(
                s.oss_access_key_id.get_secret_value(),
                s.oss_access_key_secret.get_secret_value(),
                s.oss_security_token.get_secret_value() or None,
            )
            cfg.retry_max_attempts = 1
            cfg.connect_timeout, cfg.readwrite_timeout = 10, 60
            cfg.enabled_redirect = False
            self._client = oss.Client(cfg)
        return self._client

    def oss_key(self, location):
        self.validate_oss()
        base = f"oss://{self.settings.oss_bucket}/{self.settings.oss_prefix}assets/"
        if not location.startswith(base) or not re.fullmatch(
            r"[a-f0-9]{32}\.png", location[len(base) :]
        ):
            raise StorageError("OSS 资源不属于本项目配置的 Bucket 或目录")
        return location.split("/", 3)[3]

    def write(self, resource_id: str, content: bytes) -> str:
        from studio.storage.images import safe_path

        if not re.fullmatch(r"[a-f0-9]{32}", resource_id) or len(content) > MAX_STORED_BYTES:
            raise StorageError("图片存储参数或大小不合法")
        relative = f"assets/{resource_id}.png"
        if self.settings.asset_backend == "local":
            for directory in ("tmp", "assets"):
                (self.root / directory).mkdir(parents=True, exist_ok=True)
            temporary = self.root / "tmp" / f"{resource_id}.png"
            try:
                temporary.write_bytes(content)
                temporary.replace(safe_path(self.root, relative))
            finally:
                temporary.unlink(missing_ok=True)
            return relative
        import alibabacloud_oss_v2 as oss

        key = self.settings.oss_prefix + relative
        try:
            self.client().put_object(
                oss.PutObjectRequest(
                    bucket=self.settings.oss_bucket,
                    key=key,
                    body=content,
                    content_type="image/png",
                    acl="private",
                    forbid_overwrite=True,
                )
            )
        except Exception:
            # SDK exceptions may include signed headers. Never persist/log their text.
            raise StorageError("OSS 上传失败，请检查配置、权限与网络；未保存成功记录") from None
        return f"oss://{self.settings.oss_bucket}/{key}"

    def read(self, location: str) -> bytes:
        from studio.storage.images import safe_path

        if not location.startswith("oss://"):
            return safe_path(self.root, location).read_bytes()
        import alibabacloud_oss_v2 as oss

        key = self.oss_key(location)
        try:
            response = self.client().get_object(
                oss.GetObjectRequest(bucket=self.settings.oss_bucket, key=key)
            )
            try:
                content = bytearray()
                for chunk in response.body.iter_bytes():
                    if len(content) + len(chunk) > MAX_STORED_BYTES:
                        raise StorageError("OSS 图片超过读取上限")
                    content.extend(chunk)
                return bytes(content)
            finally:
                response.body.close()
        except Exception:
            raise StorageError("OSS 图片读取失败，请检查配置、权限与网络") from None

    def read_asset(self, item) -> bytes:
        content = self.read(item["path"])
        if hashlib.sha256(content).hexdigest() != item["sha256"]:
            raise StorageError("图片内容校验失败，存储内容可能已改变")
        return content
