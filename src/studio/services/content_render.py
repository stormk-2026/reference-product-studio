"""Deterministic Chinese typography and unaltered screenshots/product assets."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

SIZE = (1152, 1536)


def chinese_font(size):
    for path in (
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
    ):
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    raise ValueError("宣传排版需要中文字体，请安装 fonts-noto-cjk 后重启 Worker")


def wrap(text, font, width):
    lines = []
    for paragraph in text.splitlines() or [""]:
        line = ""
        for char in paragraph:
            if font.getlength(line + char) > width:
                if not line:
                    raise ValueError("文字过宽，无法排版")
                lines.append(line)
                line = ""
            line += char
        lines.append(line)
    return lines


def tokens(deck):
    for heading_size in (72, 64, 56):
        font = chinese_font(heading_size)
        if all(len(wrap(p.title, font, 1000)) <= 3 for p in deck.pages):
            break
    else:
        raise ValueError("标题换行过多，请缩短标题（最多3行）")
    for body_size in (32, 30, 28):
        body_font = chinese_font(body_size)
        if all(len(wrap(p.body, body_font, 1000)) <= 5 for p in deck.pages):
            break
    else:
        raise ValueError("正文超出版面，请精简文案或减少换行（最多5行）")
    return heading_size, body_size


def render_deck(brief, deck, images, fixture=False):
    heading_size, body_size = tokens(deck)
    heading, body = chinese_font(heading_size), chinese_font(body_size)
    small = chinese_font(24)
    dark = brief.style == "bold"
    bg = "#101a2d" if dark else "#fff8ed" if brief.style == "warm" else "#f5f7fb"
    ink, muted = ("#ffffff", "#c8d4e8") if dark else ("#142033", "#526176")
    surface = "#1d2b44" if dark else "#ffffff"
    title_lines = max(len(wrap(p.title, heading, 1000)) for p in deck.pages)
    frame_top = 128 + title_lines * (heading_size + 16) + 48
    image_height = 1222 - frame_top - 72
    pages = []
    for index, page in enumerate(deck.pages):
        image = Image.new("RGB", SIZE, bg)
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((68, 62, 78, 98), radius=5, fill=brief.accent)
        draw.text(
            (98, 62),
            ("APP / " if brief.kind == "app" else "PRODUCT / ") + page.label,
            font=small,
            fill=muted,
        )
        draw.text((990, 62), f"{index + 1:02d}/{len(deck.pages):02d}", font=small, fill=muted)
        y = 128
        for line in wrap(page.title, heading, 1000):
            draw.text((72, y), line, font=heading, fill=ink)
            y += heading_size + 16
        # Image frames have a fixed size across pages; no perspective, clipping or generated UI.
        if brief.kind == "app":
            draw.rounded_rectangle((72, frame_top, 1080, 1222), radius=40, fill=surface)
            source = images[page.image_index].convert("RGBA")
            fitted = ImageOps.contain(source, (856, image_height), Image.Resampling.LANCZOS)
            x, top = (
                (1152 - fitted.width) // 2,
                frame_top + 36 + (image_height - fitted.height) // 2,
            )
            draw.rounded_rectangle(
                (x - 10, top - 10, x + fitted.width + 10, top + fitted.height + 10),
                radius=18,
                fill="#a5b4cc" if dark else "#dce3ef",
            )
        else:
            draw.rounded_rectangle((72, frame_top, 1080, 1222), radius=40, fill=surface)
            fitted = ImageOps.contain(
                images[page.image_index].convert("RGBA"),
                (936, image_height),
                Image.Resampling.LANCZOS,
            )
            x, top = (
                (1152 - fitted.width) // 2,
                frame_top + 36 + (image_height - fitted.height) // 2,
            )
        image.paste(fitted, (x, top), fitted)
        y = 1250
        for line in wrap(page.body, body, 1000):
            draw.text((72, y), line, font=body, fill=ink)
            y += body_size + 10
        if y > 1470:
            raise ValueError("正文超过安全区，请精简文字")
        if fixture:
            draw.rectangle((0, 1490, 1152, 1536), fill="#273a36")
            draw.text((72, 1496), "测试夹具 / 非真实产品内容", font=small, fill="white")
        pages.append(image)
    return pages, dict(
        width=1152,
        height=1536,
        title_size=heading_size,
        body_size=body_size,
        page_count=len(pages),
        text_overflow=False,
        image_fit="contain",
    )


def preflight_scene_deck(deck):
    """Reject known text overflow before a paid visual request is approved."""
    _, body_size = tokens(deck)
    font = chinese_font(body_size)
    for page in deck.pages:
        if 1250 + len(wrap(page.body, font, 1000)) * (body_size + 10) > 1470:
            raise ValueError("正文超过安全区，请精简文字后再预览 Seedream")


def render_scene_page(brief, deck, images, index, background):
    """Place exact source pixels and typeset text over an AI-generated visual layer."""
    page = deck.pages[index]
    heading_size, body_size = tokens(deck)
    heading, body, small = chinese_font(heading_size), chinese_font(body_size), chinese_font(24)
    visual = ImageOps.fit(background.convert("RGB"), SIZE, method=Image.Resampling.LANCZOS)
    image = visual.convert("RGBA")
    overlay = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    dark = brief.style == "bold"
    panel = (14, 22, 38, 218) if dark else (255, 255, 255, 224)
    ink = "#ffffff" if dark else "#142033"
    muted = "#e6edf6" if dark else "#43536a"
    title_lines = wrap(page.title, heading, 1000)
    title_bottom = 128 + len(title_lines) * (heading_size + 16)
    frame_top = title_bottom + 40
    draw.rounded_rectangle((42, 38, 1110, frame_top - 10), radius=36, fill=panel)
    draw.rounded_rectangle(
        (52, frame_top, 1100, 1224),
        radius=42,
        fill=(14, 22, 38, 86) if dark else (255, 255, 255, 86),
    )
    draw.rounded_rectangle((42, 1232, 1110, 1490), radius=36, fill=panel)
    draw.rounded_rectangle((68, 60, 80, 98), radius=5, fill=brief.accent)
    draw.text(
        (98, 62),
        ("APP / " if brief.kind == "app" else "PRODUCT / ") + page.label,
        font=small,
        fill=muted,
    )
    draw.text((978, 62), f"{index + 1:02d}/{len(deck.pages):02d}", font=small, fill=muted)
    y = 128
    for line in title_lines:
        draw.text((72, y), line, font=heading, fill=ink)
        y += heading_size + 16
    y = 1250
    for line in wrap(page.body, body, 1000):
        draw.text((72, y), line, font=body, fill=ink)
        y += body_size + 10
    if y > 1470:
        raise ValueError("正文超过安全区，请精简文字")
    image = Image.alpha_composite(image, overlay)
    source = images[page.image_index].convert("RGBA")
    fitted = ImageOps.contain(source, (920, 1180 - frame_top), Image.Resampling.LANCZOS)
    x, top = (SIZE[0] - fitted.width) // 2, frame_top + (1180 - frame_top - fitted.height) // 2
    if brief.kind == "app":
        border = Image.new("RGBA", SIZE, (0, 0, 0, 0))
        bd = ImageDraw.Draw(border)
        bd.rounded_rectangle(
            (x - 12, top - 12, x + fitted.width + 12, top + fitted.height + 12),
            radius=26,
            fill=(255, 255, 255, 245),
        )
        image = Image.alpha_composite(image, border)
    image.alpha_composite(fitted, (x, top))
    return image.convert("RGB"), dict(
        width=1152,
        height=1536,
        image_fit="contain",
        source_pixels="unaltered_except_uniform_resize",
        text_overflow=False,
        visual_layer="Seedream",
    )
