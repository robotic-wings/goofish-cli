"""FastMCP 入口。扫描同一 registry → 每个 Command 注册为 @mcp.tool()。

启动（推荐）：`uvx goofish-cli`  —— uvx 按 command 名找包，`goofish-cli` 匹配 PyPI
包名，一行搞定。Claude Code 配置:

  {
    "mcpServers": {
      "goofish": { "command": "uvx", "args": ["goofish-cli"] }
    }
  }

其他入口（仅在 `goofish-cli` 包已装到某 env 时可用）：
  - `python -m goofish_cli.mcp_server`
  - `goofish-mcp`（pip / uv tool install 后可用；或 `uvx --from goofish-cli goofish-mcp`）

HTTP 模式（在端口上开服，"你先跑起来、客户端来连"）：
  - `goofish-cli --http`                    # streamable-http，默认 127.0.0.1:8444
  - `goofish-cli --http --host 0.0.0.0 --port 9000`
  - `goofish-cli --http --transport sse`    # 用老的 SSE 传输
不加 `--http` 时仍是 stdio —— Claude Desktop / Claude Code 的本地 spawn 配置不受影响。

HTTPS：找得到 TLS 证书就自动走 https，否则退回明文 http（带告警）。用 mkcert
签本地受信任证书：
  - `mkcert -install`   # 一次性：安装本地 CA
  - `mkcert -cert-file certs/localhost-cert.pem -key-file certs/localhost-key.pem localhost 127.0.0.1 ::1`
默认从 `certs/localhost-cert.pem` / `certs/localhost-key.pem` 读取，也可用 `--tls-cert`
/ `--tls-key` 指定路径。

注意：`uvx goofish-mcp` 单写会因 PyPI 无同名包而解析失败——不是别名能救的，这是 uvx
按 command 名查包的默认行为决定的。
"""
from __future__ import annotations

import argparse
import asyncio
import inspect
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from goofish_cli.core import GoofishError, iter_commands
from goofish_cli.core.registry import discover

mcp = FastMCP("goofish")


def _register_all() -> None:
    discover()
    for cmd in iter_commands():
        _register_one(cmd)


def _register_one(cmd) -> None:
    """把一条 registry Command 注册为 MCP tool，保留参数签名。

    handler 是 async（FastMCP 要求），但 registry 里的 cmd.func 是同步函数——
    其中有些（`message list-chats --watch-secs` / `search items` / `item view`）
    内部用 `asyncio.run(...)` 驱动 async 逻辑。直接 `cmd.func(**kwargs)` 会在
    MCP 的事件循环里再起一个 event loop，触发 `RuntimeError: asyncio.run() cannot
    be called from a running event loop`。

    用 `asyncio.to_thread` 把同步调用扔线程池，即可绕开嵌套 loop 限制，同时
    对纯 HTTP 命令（没有 asyncio.run 的）也零成本兼容。
    """
    tool_name = f"{cmd.namespace}_{cmd.name}".replace("-", "_")
    doc = cmd.description
    sig = inspect.signature(cmd.func)

    async def handler(**kwargs: Any) -> dict[str, Any]:
        try:
            result = await asyncio.to_thread(cmd.func, **kwargs)
            return {"ok": True, "data": result}
        except GoofishError as e:
            return {"ok": False, "error_type": type(e).__name__, "message": str(e)}

    handler.__name__ = tool_name
    handler.__doc__ = doc
    handler.__signature__ = sig  # type: ignore[attr-defined]

    mcp.tool(name=tool_name, description=doc)(handler)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="goofish-cli", description="goofish MCP server")
    p.add_argument(
        "--http",
        action="store_true",
        help="在端口上以 HTTP 方式开服（默认不加则走 stdio，供 Claude Desktop 等 spawn）",
    )
    p.add_argument(
        "--transport",
        choices=["streamable-http", "sse"],
        default="streamable-http",
        help="--http 时使用的传输方式（默认 streamable-http）",
    )
    p.add_argument("--host", default="127.0.0.1", help="HTTP 监听地址（默认 127.0.0.1）")
    p.add_argument("--port", type=int, default=8444, help="HTTP 监听端口（默认 8444）")
    p.add_argument(
        "--tls-cert",
        default="certs/localhost-cert.pem",
        help="TLS 证书路径（PEM）。与 --tls-key 都存在时以 HTTPS 开服，否则退回明文 HTTP",
    )
    p.add_argument(
        "--tls-key",
        default="certs/localhost-key.pem",
        help="TLS 私钥路径（PEM）",
    )
    return p.parse_args(argv)


def _run_http(args: argparse.Namespace) -> None:
    """HTTP 模式。找得到 TLS 证书 → 用 uvicorn 直接开 HTTPS；否则退回 FastMCP 明文 http。

    FastMCP 的 Settings 不暴露 SSL 选项，所以 HTTPS 时绕过 `mcp.run()`，自己取
    ASGI app（streamable_http_app / sse_app）交给 uvicorn，并传 ssl_certfile/keyfile。
    """
    mcp.settings.host = args.host
    mcp.settings.port = args.port

    cert_ok = bool(args.tls_cert) and os.path.isfile(args.tls_cert)
    key_ok = bool(args.tls_key) and os.path.isfile(args.tls_key)

    if not (cert_ok and key_ok):
        # 证书缺失：退回明文 http（沿用 FastMCP 自带的 run），给出告警。
        print(
            f"[HTTP] 未找到 TLS 证书（cert={args.tls_cert} key={args.tls_key}），"
            "以明文 HTTP 运行",
            flush=True,
        )
        mcp.run(transport=args.transport)
        return

    import uvicorn

    app = mcp.sse_app() if args.transport == "sse" else mcp.streamable_http_app()

    print(
        f"goofish MCP server running on https://{args.host}:{args.port} "
        f"(transport={args.transport})",
        flush=True,
    )
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        ssl_certfile=args.tls_cert,
        ssl_keyfile=args.tls_key,
        log_level=mcp.settings.log_level.lower(),
    )


def main() -> None:
    args = _parse_args()
    _register_all()

    if args.http:
        # "你先开着、客户端来连" 模式：适合远程 / 一个 server 多客户端 / 跑在容器里。
        _run_http(args)
    else:
        # 默认 stdio："客户端 spawn 你"，Claude Desktop / Claude Code 的本地配置走这条。
        mcp.run()


if __name__ == "__main__":
    main()
