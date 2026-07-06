from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def default_downloads() -> Path:
    return Path.home() / "Downloads"


def default_state_file() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".ozon-helper")
    return root / "ozon-helper" / "chatgpt_download_watcher.json"


def load_state(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"uploaded": {}}


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def mcp_call(url: str, tool: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "jsonrpc": "2.0",
        "id": int(time.time() * 1000) % 1000000,
        "method": "tools/call",
        "params": {"name": tool, "arguments": arguments or {}},
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
        text = resp.read().decode("utf-8", errors="replace")
    for line in text.splitlines():
        if line.startswith("data: "):
            msg = json.loads(line[6:])
            result = msg.get("result") or {}
            structured = result.get("structuredContent")
            if isinstance(structured, dict):
                return structured
            content = result.get("content") or []
            if content and isinstance(content[0], dict):
                raw = content[0].get("text")
                if raw:
                    try:
                        return json.loads(raw)
                    except Exception:
                        return {"text": raw}
            return result
    raise RuntimeError(f"No MCP data event returned: {text[:300]}")


def stable_file(path: Path, stable_seconds: float) -> bool:
    try:
        first = path.stat()
        if first.st_size <= 0:
            return False
        time.sleep(stable_seconds)
        second = path.stat()
        return first.st_size == second.st_size and first.st_mtime == second.st_mtime
    except OSError:
        return False


def newest_candidate(
    watch_dir: Path,
    target_created_at: float,
    uploaded: dict[str, Any],
    expected_file_name: str | None = None,
) -> Path | None:
    if expected_file_name:
        expected = watch_dir / expected_file_name
        if expected.is_file() and expected.suffix.lower() in IMAGE_SUFFIXES and str(expected) not in uploaded:
            return expected
    files: list[Path] = []
    for path in watch_dir.iterdir():
        if not path.is_file() or path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        if str(path) in uploaded:
            continue
        try:
            if path.stat().st_mtime + 2 < target_created_at:
                continue
        except OSError:
            continue
        files.append(path)
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def upload_file(mcp_url: str, path: Path, target: dict[str, Any]) -> dict[str, Any]:
    data = path.read_bytes()
    encoded = base64.b64encode(data).decode("ascii")
    return mcp_call(
        mcp_url,
        "upload_chatgpt_downloaded_image",
        {
            "image_base64": encoded,
            "filename": path.name,
            "draft_id": target.get("draft_id"),
            "slot_id": target.get("slot_id"),
            "image_type": target.get("image_type"),
            "task_id": target.get("task_id"),
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Watch ChatGPT downloads and upload the next image to ozon-helper.")
    parser.add_argument("--mcp-url", default="https://mcp.ryda.top/mcp")
    parser.add_argument("--watch-dir", type=Path, default=default_downloads())
    parser.add_argument("--state-file", type=Path, default=default_state_file())
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--stable-seconds", type=float, default=1.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    if not args.watch_dir.exists():
        print(f"watch dir not found: {args.watch_dir}", file=sys.stderr)
        return 2
    state = load_state(args.state_file)
    uploaded = state.setdefault("uploaded", {})
    print(f"watching {args.watch_dir}")
    print(f"mcp {args.mcp_url}")

    while True:
        try:
            target_resp = mcp_call(args.mcp_url, "get_chatgpt_image_target")
            target = target_resp.get("target") or {}
            if not target.get("draft_id"):
                if args.once:
                    print("no active target")
                    return 1
                time.sleep(args.interval)
                continue
            candidate = newest_candidate(
                args.watch_dir,
                float(target.get("created_at") or 0),
                uploaded,
                str(target.get("file_name") or ""),
            )
            if candidate is None:
                if args.once:
                    print(f"target active, no new image yet: draft={target.get('draft_id')} slot={target.get('slot_id')}")
                    return 1
                time.sleep(args.interval)
                continue
            if not stable_file(candidate, args.stable_seconds):
                time.sleep(args.interval)
                continue
            suffix = f" task {target.get('task_id')}" if target.get("task_id") else ""
            print(f"uploading {candidate} -> draft {target.get('draft_id')} slot {target.get('slot_id')}{suffix}")
            result = upload_file(args.mcp_url, candidate, target)
            uploaded[str(candidate)] = {"at": time.time(), "result": result}
            save_state(args.state_file, state)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            if args.once:
                return 0
        except (urllib.error.URLError, TimeoutError, RuntimeError, ValueError) as exc:
            print(f"watch error: {exc}", file=sys.stderr)
            if args.once:
                return 1
            time.sleep(max(args.interval, 5.0))


if __name__ == "__main__":
    raise SystemExit(main())
