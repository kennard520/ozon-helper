"""Runtime flags shared by the local launcher and application."""
import os


def is_local_lite() -> bool:
    return os.environ.get("OZON_LOCAL_LITE", "").strip().lower() in {"1", "true", "yes"}
