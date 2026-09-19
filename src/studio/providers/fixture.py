from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from studio.domain.models import (
    ANALYSIS_FIELDS,
    RECIPE_FIELDS,
    Analysis,
    Evidence,
    Recipe,
    RecipeElement,
)


def font(size=24):
    for path in ["/System/Library/Fonts/PingFang.ttc", "/System/Library/Fonts/STHeiti Light.ttc"]:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def stamp(image, extra=""):
    image = image.copy().convert("RGBA")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, image.width, 82), fill="#263a36")
    draw.text((20, 12), "FIXTURE · 测试夹具 / 非模型生成", font=font(22), fill="white")
    draw.text(
        (20, 45), extra[:60] or "仅验证工作流，不代表真实视觉效果", font=font(17), fill="white"
    )
    return image


class FixtureProvider:
    name = "fixture"
    model = "fixture-visual-v1"
    capabilities = {"understand", "generate", "edit", "multi_image", "mask"}

    def analyze(self, product_ids, notes):
        return Analysis(
            fields={
                name: Evidence(
                    note="Fixture 未分析图片，待真实模型或用户确认", asset_ids=product_ids
                )
                for name in ANALYSIS_FIELDS
            },
            dimensions=[{"部位": "待填写", "数值": None, "单位": "cm", "来源": "unknown"}],
            workmanship=[{"工艺": "待填写", "说明": None, "来源": "unknown"}],
            notes=notes,
        )

    def recipe(self, preserve):
        return Recipe(
            elements={key: RecipeElement() for key in RECIPE_FIELDS},
            preserve=preserve,
            exclude="参考图中的品牌、文字和原商品",
        )

    def render(self, mode, size, background, label):
        image = Image.new("RGBA", size, background)
        draw = ImageDraw.Draw(image)
        w, h = size
        if mode.startswith("A_"):
            if mode == "A_pattern":
                draw.polygon(
                    [
                        (w * 0.14, h * 0.28),
                        (w * 0.38, h * 0.24),
                        (w * 0.43, h * 0.78),
                        (w * 0.12, h * 0.78),
                    ],
                    fill="#f9f6ed",
                    outline="#345a52",
                    width=4,
                )
                draw.polygon(
                    [
                        (w * 0.57, h * 0.24),
                        (w * 0.81, h * 0.28),
                        (w * 0.84, h * 0.78),
                        (w * 0.54, h * 0.78),
                    ],
                    fill="#f9f6ed",
                    outline="#345a52",
                    width=4,
                )
                draw.text(
                    (28, h - 85), "未经版师验证，不可直接裁剪生产", font=font(22), fill="#852d22"
                )
                draw.text(
                    (28, h - 50),
                    "无测量、无放码、无缝份；固定测试轮廓",
                    font=font(18),
                    fill="#852d22",
                )
            else:
                draw.polygon(
                    [
                        (w * 0.35, h * 0.25),
                        (w * 0.2, h * 0.36),
                        (w * 0.29, h * 0.5),
                        (w * 0.36, h * 0.45),
                        (w * 0.36, h * 0.8),
                        (w * 0.66, h * 0.8),
                        (w * 0.66, h * 0.45),
                        (w * 0.73, h * 0.5),
                        (w * 0.82, h * 0.36),
                        (w * 0.66, h * 0.25),
                        (w * 0.57, h * 0.3),
                        (w * 0.45, h * 0.3),
                    ],
                    fill="#faf8f0",
                    outline="#345a52",
                    width=4,
                )
                if mode == "A_front":
                    draw.line((w * 0.51, h * 0.31, w * 0.51, h * 0.8), fill="#345a52", width=3)
                draw.text(
                    (30, h - 52), "固定示意轮廓 · 并非输入服装的还原", font=font(20), fill="#345a52"
                )
        else:
            draw.ellipse((w * 0.12, h * 0.6, w * 0.88, h * 0.84), fill="#cec5b6")
            draw.rectangle((w * 0.23, h * 0.47, w * 0.77, h * 0.7), fill="#faf5ea")
            draw.text((w * 0.25, h * 0.49), "FIXTURE SCENE", font=font(24), fill="#54645d")
        return stamp(image, label)
