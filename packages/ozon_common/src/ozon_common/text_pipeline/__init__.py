"""text_pipeline — 文本/多模态处理管线（纯注入式，不依赖框架）。"""

from ozon_common.text_pipeline.understand import (
    SYS_UNDERSTAND,
    build_understand_input,
    parse_understanding,
    understand,
)
from ozon_common.text_pipeline.ai_card import (
    NO_BRAND,
    _SYS_NAV,
    _extract_json,
    _node_name,
    _parse_index,
    navigate_category,
    build_profile,
    assemble_attributes,
    clean_hashtags,
)

from ozon_common.text_pipeline.pipeline import STEPS, run_text_pipeline  # noqa: F401

__all__ = [
    "SYS_UNDERSTAND",
    "build_understand_input",
    "parse_understanding",
    "understand",
    "NO_BRAND",
    "_SYS_NAV",
    "_extract_json",
    "_node_name",
    "_parse_index",
    "navigate_category",
    "build_profile",
    "assemble_attributes",
    "clean_hashtags",
    "STEPS",
    "run_text_pipeline",
]
