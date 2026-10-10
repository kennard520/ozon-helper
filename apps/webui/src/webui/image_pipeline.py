"""图片管线串联：源图 → 抠图 → 主图(无水印) + 信息图/场景图(加水印) → 一组 Ozon 商品图。

联网的两步（cutout 抠图、make_scene 出场景图）以参数注入，便于离线单测；
纯 PIL 合成（主图/信息图/水印）直接复用 backend.image_compose。
OSS 上传 + 回填 draft.images 是更上层的薄封装（单独做，触及真实 OSS/草稿）。
"""
from __future__ import annotations

from typing import Callable, Iterable, Tuple

from webui.image_compose import add_watermark, compose_infographic


def assemble_images(
    source_ref: str, *, shop_name: str,
    make_main: Callable[[str], bytes],
    infographics: Iterable[dict] = (), scenes: Iterable[str] = (),
    make_scene: Callable[[str, str], bytes] | None = None,
    font_path: str | None = None, canvas: Tuple[int, int] = (1024, 1536),
    fmt: str = "JPEG",
) -> list[bytes]:
    """产出一组商品图（bytes）：主图在前且**无水印**；信息图 / 场景图加店铺水印。

    注入项（联网）：
      - make_main(source_ref) -> 白底主图 bytes（gen_image.generate_main）
      - make_scene(source_ref, prompt) -> 场景图 bytes（gen_image.generate_scene），缺省则跳过场景图
    信息图用主图当底图（产品可见）+ 底部俄语文字面板。infographics: 可迭代 {heading, bullets}。
    （gpt-image-2-2 不支持透明，故不抠图；主图即白底 edit 结果。）
    """
    main = make_main(source_ref)
    images: list[bytes] = [main]                                              # 主图：无水印
    for info in infographics:
        ig = compose_infographic(
            main, canvas=canvas, heading=info.get("heading", ""),
            bullets=info.get("bullets", ()), font_path=font_path, fmt=fmt)
        images.append(add_watermark(ig, shop_name, fmt=fmt))                  # 副图：加水印
    if make_scene:
        for prompt in scenes:
            images.append(add_watermark(make_scene(source_ref, prompt), shop_name, fmt=fmt))
    return images


def upload_images(images: Iterable[bytes], upload_fn: Callable[[bytes, str], str],
                  *, ext: str = "jpg") -> list[str]:
    """把一组图字节逐张上传，返回公网 URL 列表（保持顺序，主图在前）。
    upload_fn(bytes, ext) -> url 注入（生产 = OssClient.upload_bytes，内容 MD5 幂等去重）。"""
    return [upload_fn(b, ext) for b in images]
