# MCP 接入指南

## Claude Code / Codex CLI

在 `~/.claude/settings.json` 或项目 `.claude/settings.json` 加：

```json
{
  "mcpServers": {
    "goofish": {
      "command": "uvx",
      "args": ["goofish-cli"]
    }
  }
}
```

或本地开发版：

```json
{
  "mcpServers": {
    "goofish": {
      "command": "/Users/you/Desktop/goofish-cli/.venv/bin/goofish-cli"
    }
  }
}
```

## Cursor

`~/.cursor/mcp.json`：同上格式。

## HTTP / HTTPS 模式（自己开服，客户端来连）

默认走 stdio（客户端 spawn 本进程）。也可以在端口上开一个长驻服务，供远程 /
多客户端 / 容器场景连接：

```bash
goofish-cli --http                          # streamable-http，默认 127.0.0.1:8444
goofish-cli --http --host 0.0.0.0 --port 9000
goofish-cli --http --transport sse          # 老的 SSE 传输
```

MCP 端点在 `/mcp`（SSE 传输时按 FastMCP 默认路径）。

### HTTPS（mkcert 本地证书）

找得到 TLS 证书就自动以 **HTTPS** 开服，否则退回明文 HTTP（带告警）。用
[mkcert](https://github.com/FiloSottile/mkcert) 签一张本地受信任的证书：

```bash
mkcert -install    # 一次性：安装本地 CA
mkcert -cert-file certs/localhost-cert.pem -key-file certs/localhost-key.pem localhost 127.0.0.1 ::1
```

默认从 `certs/localhost-cert.pem` / `certs/localhost-key.pem` 读取，也可显式指定：

```bash
goofish-cli --http --tls-cert /path/to/cert.pem --tls-key /path/to/key.pem
# → https://127.0.0.1:8444/mcp
```

`certs/` 已在 `.gitignore` 中，私钥不会被提交。

## 可用工具

启动后 Claude 获得以下 tool：

| Tool 名 | 说明 |
|---|---|
| `auth_login` | 导入 cookie |
| `auth_status` | 检查登录态 |
| `auth_reset_guard` | 解除风控熔断 |
| `item_get` | 查询商品（只读） |
| `item_publish` | 发布商品（写） |
| `item_delete` | 下架商品（写） |
| `media_upload` | 上传图片 |
| `category_recommend` | AI 类目识别 |
| `location_default` | 获取默认地址 |

## 首次使用

1. 从 Chrome DevTools 导出 goofish.com cookie（JSON 数组）到本地文件
2. 跑一次 CLI 导入：`goofish auth login ~/Downloads/goofish-cookies.json`
3. Claude 会话里问："帮我查一下 itemId 1046118265141 的商品信息"
4. Claude 会自动调用 `item_get` tool

## 调试

列出所有注册的 tool：

```bash
python -c "
from goofish_cli.mcp_server import mcp, _register_all
import asyncio
_register_all()
for t in asyncio.run(mcp.list_tools()):
    print(t.name)
"
```
