"""向后兼容：understand 已下沉到 ozon_common.text_pipeline.understand。"""
from ozon_common.text_pipeline.understand import (  # noqa: F401
    SYS_UNDERSTAND,
    build_understand_input,
    parse_understanding,
    understand,
)
