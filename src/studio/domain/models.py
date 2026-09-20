from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Evidence(StrictModel):
    value: str | None = None
    status: Literal["user_confirmed", "observed", "inferred", "unknown"] = "unknown"
    asset_ids: list[str] = Field(default_factory=list)
    note: str = ""


class RecipeElement(StrictModel):
    value: str | None = None
    action: Literal["inherit", "modify", "ignore"] = "inherit"
    override: str | None = None


RECIPE_FIELDS = {
    "scene_type": "场景类型",
    "subject_position": "主体位置",
    "subject_fraction": "画面占比（视觉估计）",
    "camera": "机位类别（视觉估计）",
    "negative_space": "留白",
    "light_direction": "光源方向",
    "light_softness": "光线软硬",
    "contrast": "明暗对比",
    "background": "背景颜色和材质",
    "props": "道具类别与相对位置",
    "colors": "色彩关系",
    "depth": "景深表现",
}
# Generic Fixture placeholders only; real analysis fields are category-dependent.
ANALYSIS_FIELDS = ["商品类别", "外观与配色", "可见结构", "图中文字", "需补充的信息"]
PATTERN_WARNING = "未经版师验证，不可直接裁剪生产"
FIXTURE_WARNING = "测试夹具 / 非模型生成；不代表对输入图片的真实分析或生成效果"


class Recipe(StrictModel):
    elements: dict[str, RecipeElement] = Field(default_factory=dict)
    preserve: str = Field(default="", max_length=4000)
    exclude: str = Field(default="", max_length=4000)


class Analysis(StrictModel):
    generation_prompt: str = Field(default="", max_length=8000)
    fields: dict[str, Evidence]
    dimensions: list[dict[str, str | None]] = Field(default_factory=list)
    workmanship: list[dict[str, str | None]] = Field(default_factory=list)
    notes: str = ""


class Request(StrictModel):
    execution: Literal["fixture", "real"] = "fixture"
    mode: Literal[
        "A",
        "A_front",
        "A_back",
        "A_pattern",
        "A_white",
        "A_views",
        "CUTOUT",
        "CHECK",
        "B1",
        "B2",
        "C_analyze",
        "C1",
        "C2",
    ]
    check_candidate_id: str | None = None
    product_ids: list[str] = Field(min_length=1, max_length=10)
    product_view_ids: list[str] = Field(default_factory=list, max_length=8)
    background_id: str | None = None
    subject_id: str | None = None
    change_background: bool = True
    change_subject: bool = False
    anchor_candidate_id: str | None = None
    batch_product_ids: list[str] = Field(default_factory=list, max_length=10)
    batch_index: int = Field(default=0, ge=0, le=9)
    reference_id: str | None = None
    back_id: str | None = None
    mask_id: str | None = None
    analysis_id: str | None = None
    recipe_id: str | None = None
    instructions: str = Field(default="", max_length=8000)
    preserve: str = Field(default="", max_length=4000)
    strategy: Literal["reference_recipe", "text_only"] = "reference_recipe"
    ratio: Literal["1:1", "4:5", "16:9"] = "1:1"
    scale: float = Field(default=0.7, ge=0.1, le=0.9)
    x: float = Field(default=0.5, ge=0, le=1)
    y: float = Field(default=0.5, ge=0, le=1)
    feather: float = Field(default=0, ge=0, le=4)
    shadow: bool = True
    background: str = Field(default="#e9e2d8", pattern=r"^#[0-9a-fA-F]{6}$")


class Evaluation(StrictModel):
    fidelity: int | None = Field(default=None, ge=1, le=5)
    reference_fit: int | None = Field(default=None, ge=1, le=5)
    usability: int | None = Field(default=None, ge=1, le=5)
    rework_minutes: float | None = Field(default=None, ge=0, le=10000)
    notes: str = Field(default="", max_length=8000)
    checks: dict[str, Literal["pass", "fail", "unknown"]] = Field(default_factory=dict)


class CheckItem(StrictModel):
    topic: str = Field(max_length=100)
    status: Literal["issue", "no_obvious_issue", "unknown"]
    observation: str = Field(max_length=2000)
    location: str = Field(max_length=500)
    asset_ids: list[str] = Field(max_length=12)
    suggestion: str = Field(default="", max_length=1000)


class QualityCheck(StrictModel):
    summary: str = Field(min_length=1, max_length=2000)
    checks: list[CheckItem] = Field(min_length=1, max_length=20)
    limitations: str = Field(min_length=1, max_length=2000)
