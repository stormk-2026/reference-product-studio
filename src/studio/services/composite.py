from PIL import Image, ImageFilter


def composite(product, background, request, mask=None):
    subject = product.convert("RGBA")
    if mask is not None:
        if mask.size != subject.size:
            raise ValueError("蒙版必须与商品图像素尺寸一致")
        subject.putalpha(mask.convert("L"))
    elif subject.getchannel("A").getextrema()[0] == 255:
        raise ValueError("主体保留合成需要透明图或同尺寸蒙版；自动抠图尚不支持")
    if subject.getchannel("A").getextrema()[1] == 0:
        raise ValueError("主体完全透明，请提供有效商品图或蒙版")
    log = ["alpha 合成；未对主体调色；未生成新视角"]
    if request.feather:
        subject.putalpha(subject.getchannel("A").filter(ImageFilter.GaussianBlur(request.feather)))
        log.append(f"边缘羽化：{request.feather}px")
    max_w, max_h = background.width * request.scale, (background.height - 92) * request.scale
    factor = min(max_w / subject.width, max_h / subject.height)
    size = (max(1, round(subject.width * factor)), max(1, round(subject.height * factor)))
    subject = subject.resize(size, Image.Resampling.LANCZOS)
    log.append(f"LANCZOS 重采样：{product.size} → {size}；不保证所有像素不变")
    x = round((background.width - subject.width) * request.x)
    y = 92 + round((background.height - 92 - subject.height) * request.y)
    output = background.convert("RGBA").copy()
    if request.shadow:
        layer = Image.new("RGBA", output.size, (0, 0, 0, 0))
        shade = Image.new("RGBA", subject.size, (28, 32, 29, 0))
        shade.putalpha(subject.getchannel("A").point(lambda a: round(a * 0.23)))
        layer.alpha_composite(shade, (x + 10, y + 14))
        output = Image.alpha_composite(output, layer.filter(ImageFilter.GaussianBlur(12)))
        log.append("本地投影：右下偏移 (10,14)，模糊12px；主体光照未重绘")
    output.alpha_composite(subject, (x, y))
    log.append(f"位置：({x},{y})；画布：{output.size}")
    return output, log
