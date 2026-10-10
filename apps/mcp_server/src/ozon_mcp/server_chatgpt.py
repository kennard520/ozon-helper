from __future__ import annotations

import logging
import os
import sys

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from ozon_mcp.tools import CHATGPT_TOOL_NAMES, register_tools

log = logging.getLogger("ozon.mcp.chatgpt")


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = os.environ.get(name)
    if not raw:
        return default
    return [x.strip() for x in raw.split(",") if x.strip()]


def _transport_security() -> TransportSecuritySettings:
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=(os.environ.get("OZON_MCP_DISABLE_DNS_REBINDING_PROTECTION") != "1"),
        allowed_hosts=_env_list("OZON_MCP_ALLOWED_HOSTS", ["127.0.0.1:*", "localhost:*", "[::1]:*"]),
        allowed_origins=_env_list("OZON_MCP_ALLOWED_ORIGINS", ["http://127.0.0.1:*", "http://localhost:*"]),
    )


mcp = FastMCP(
    "ozon-helper-chatgpt",
    host=os.environ.get("OZON_MCP_HOST") or "127.0.0.1",
    port=_env_int("OZON_MCP_PORT", 8586),
    stateless_http=True,
    transport_security=_transport_security(),
)
register_tools(mcp, include_tools=CHATGPT_TOOL_NAMES)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [ozon-mcp-chatgpt] %(levelname)s %(message)s",
        stream=sys.stderr,
        force=True,
    )
    host = mcp.settings.host
    port = mcp.settings.port
    log.info("starting ozon-helper ChatGPT MCP server on %s:%s with %s tools", host, port, len(CHATGPT_TOOL_NAMES))
    mcp.run(transport="streamable-http")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
