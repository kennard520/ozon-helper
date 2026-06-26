"""图片合成（PIL）：透明抠图 → 白底主图 / 副图加店铺水印。

- compose_main_white: 把透明产品图居中贴到白底画布（Ozon 主图，3:4，留安全边）。**主图不加水印/文字**。
- add_watermark:      给副图右下角叠半透明店铺名水印。
字体：传 font_path（如 Montserrat .ttf）；缺省退回 PIL 内置字体。
"""
from __future__ import annotations

import io
from typing import Iterable, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont


def _to_bytes(img: Image.Image, fmt: str = "JPEG", quality: int = 92) -> bytes:
    buf = io.BytesIO()
    save_fmt = "JPEG" if fmt.upper() in ("JPG", "JPEG") else fmt.upper()
    if save_fmt == "JPEG" and img.mode != "RGB":
        img = img.convert("RGB")
    img.save(buf, format=save_fmt, **({"quality": quality} if save_fmt == "JPEG" else {}))
    return buf.getvalue()


def _load_font(font_path: str | None, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if font_path:
        try:
            return ImageFont.truetype(font_path, size)
        except Exception:  # noqa: BLE001 - 缺字体退回内置，不让水印拖垮整条管线
            pass
    try:
        return ImageFont.load_default(size)   # Pillow ≥10 支持 size
    except TypeError:
        return ImageFont.load_default()


def compose_main_white(
    product_png: bytes, *, canvas: Tuple[int, int] = (1024, 1536),
    margin_ratio: float = 0.12, bg: Tuple[int, int, int] = (255, 255, 255),
    fmt: str = "JPEG", quality: int = 92,
) -> bytes:
    """透明产品图 → 居中贴白底画布，按 margin_ratio 留安全边，等比缩放铺满安全区。"""
    prod = Image.open(io.BytesIO(product_png)).convert("RGBA")
    cw, ch = canvas
    mx, my = int(cw * margin_ratio), int(ch * margin_ratio)
    avail_w, avail_h = max(1, cw - 2 * mx), max(1, ch - 2 * my)
    pw, ph = prod.size
    scale = min(avail_w / pw, avail_h / ph)
    nw, nh = max(1, int(pw * scale)), max(1, int(ph * scale))
    prod = prod.resize((nw, nh), Image.LANCZOS)
    canvas_img = Image.new("RGB", (cw, ch), bg)
    canvas_img.paste(prod, ((cw - nw) // 2, (ch - nh) // 2), prod)  # 用 alpha 作蒙版
    return _to_bytes(canvas_img, fmt, quality)


def add_watermark(
    image_bytes: bytes, text: str, *, font_path: str | None = None, font_size: int | None = None,
    opacity: int = 140, margin: int = 24, color: Tuple[int, int, int] = (255, 255, 255),
    fmt: str = "JPEG", quality: int = 92,
) -> bytes:
    """副图右下角叠半透明店铺名水印。opacity 0–255。"""
    base = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    fs = font_size or max(16, base.size[0] // 28)
    font = _load_font(font_path, fs)
    box = draw.textbbox((0, 0), text, font=font)
    tw, th = box[2] - box[0], box[3] - box[1]
    x = max(margin, base.size[0] - tw - margin)
    y = max(margin, base.size[1] - th - margin)
    draw.text((x, y), text, font=font, fill=(color[0], color[1], color[2], int(opacity)))
    out = Image.alpha_composite(base, overlay)
    return _to_bytes(out, fmt, quality)


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: float) -> list[str]:
    """按像素宽度把一行文字折成多行（按空格断词；超长单词独占一行）。"""
    words = str(text).split()
    lines: list[str] = []
    cur = ""
    for w in words:
        trial = (cur + " " + w).strip()
        if not cur or draw.textlength(trial, font=font) <= max_width:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


def compose_infographic(
    bg: bytes | None = None, *, canvas: Tuple[int, int] = (1024, 1536),
    heading: str = "", bullets: Iterable[str] = (), font_path: str | None = None,
    heading_size: int | None = None, body_size: int | None = None, pad: int = 64,
    panel_alpha: int = 150, text_color: Tuple[int, int, int] = (255, 255, 255),
    panel_color: Tuple[int, int, int] = (20, 22, 28), fmt: str = "JPEG", quality: int = 92,
) -> bytes:
    """俄语信息图：底图（或浅灰底）上，底部叠半透明面板 + 俄语标题 + 要点。字体优先 font_path（Montserrat）。"""
    cw, ch = canvas
    if bg:
        base = Image.open(io.BytesIO(bg)).convert("RGB").resize((cw, ch))
    else:
        base = Image.new("RGB", (cw, ch), (240, 242, 245))
    base = base.convert("RGBA")

    overlay = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    hs = heading_size or max(28, cw // 16)
    bs = body_size or max(20, cw // 26)
    hfont = _load_font(font_path, hs)
    bfont = _load_font(font_path, bs)
    max_w = cw - 2 * pad

    rows: list[tuple[str, str]] = []
    for ln in wrap_text(draw, heading, hfont, max_w):
        rows.append(("h", ln))
    for b in bullets:
        for i, ln in enumerate(wrap_text(draw, "• " + str(b), bfont, max_w)):
            rows.append(("b", ln if i == 0 else "   " + ln))

    line_h_h, line_h_b = hs + 14, bs + 10
    total_h = sum(line_h_h if t == "h" else line_h_b for t, _ in rows) + 2 * pad
    total_h = min(total_h, ch)
    y0 = ch - total_h
    draw.rectangle([0, y0, cw, ch], fill=(panel_color[0], panel_color[1], panel_color[2], int(panel_alpha)))

    y = y0 + pad
    for t, ln in rows:
        draw.text((pad, y), ln, font=(hfont if t == "h" else bfont),
                  fill=(text_color[0], text_color[1], text_color[2], 255))
        y += line_h_h if t == "h" else line_h_b

    return _to_bytes(Image.alpha_composite(base, overlay), fmt, quality)
