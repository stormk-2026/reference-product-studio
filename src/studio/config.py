import os
from pathlib import Path
from typing import Literal, Mapping

from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field, SecretStr

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)

    # Default remains Fixture. Real jobs require a request-bound confirmation token.
    mode: Literal["fixture"] = "fixture"
    storage_dir: Path
    moonshot_api_key: SecretStr = Field(default=SecretStr(""), exclude=True, repr=False)
    moonshot_base_url: str = "https://api.moonshot.cn/v1"
    kimi_model: str = "kimi-k3"
    ark_api_key: SecretStr = Field(default=SecretStr(""), exclude=True, repr=False)
    ark_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    seedream_model: str = ""


def load_settings(
    env_file: Path | None = None, *, environ: Mapping[str, str] | None = None
) -> Settings:
    """Read only the explicit project .env, never search parents or other applications."""
    env_file = env_file if env_file is not None else PROJECT_ROOT / ".env"
    local = dotenv_values(env_file, interpolate=False) if env_file.is_file() else {}
    environment = os.environ if environ is None else environ

    def value(name, default=""):
        return environment.get(name, local.get(name) or default)

    storage = Path(value("STUDIO_DATA_DIR", "./data"))
    if not storage.is_absolute():
        storage = env_file.parent / storage
    return Settings(
        storage_dir=storage.resolve(),
        moonshot_api_key=SecretStr(value("MOONSHOT_API_KEY")),
        moonshot_base_url=value("MOONSHOT_BASE_URL", "https://api.moonshot.cn/v1"),
        kimi_model=value("KIMI_MODEL", "kimi-k3"),
        ark_api_key=SecretStr(value("ARK_API_KEY")),
        ark_base_url=value("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"),
        seedream_model=value("SEEDREAM_MODEL"),
    )


def data_dir() -> Path:
    return load_settings().storage_dir


if __name__ == "__main__":
    settings = load_settings()
    # Presence only: no key content, prefixes, lengths, or network checks.
    print("默认模式：Fixture；真实适配器须在工作台逐次预览并确认才会调用。")
    for name, configured in [
        ("MOONSHOT_API_KEY", bool(settings.moonshot_api_key.get_secret_value())),
        ("ARK_API_KEY", bool(settings.ark_api_key.get_secret_value())),
        ("SEEDREAM_MODEL", bool(settings.seedream_model)),
    ]:
        print(f"{name}: {'已填写（未联网验证）' if configured else '未填写'}")
