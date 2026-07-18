"""用户配置：~/.goofish-cli/config.json。

目前只有 block_on_vpn 一项（开着 Clash/VPN 代理时拒绝执行闲鱼操作的防呆开关）。
取值优先级：环境变量 > 配置文件 > 默认值。环境变量方便 CI / 一次性覆盖，
配置文件用于持久化（每次跑 CLI 都是新进程，改完下次即生效）。

配置文件示例：
    {"block_on_vpn": true}
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

CONFIG_PATH = Path.home() / ".goofish-cli" / "config.json"

_TRUTHY = {"1", "true", "on", "yes", "y"}
_FALSY = {"0", "false", "off", "no", "n"}


@lru_cache(maxsize=1)
def _load_file() -> dict[str, Any]:
    try:
        data = json.loads(CONFIG_PATH.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        s = value.strip().lower()
        if s in _TRUTHY:
            return True
        if s in _FALSY:
            return False
    return None


def get_bool(key: str, env: str, default: bool = False) -> bool:
    """按 env > 文件 > default 解析一个布尔配置。"""
    env_val = os.environ.get(env)
    if env_val is not None:
        parsed = _as_bool(env_val)
        if parsed is not None:
            return parsed
    file_val = _as_bool(_load_file().get(key))
    if file_val is not None:
        return file_val
    return default


def block_on_vpn() -> bool:
    """开着 Clash 类代理时是否拒绝执行闲鱼操作。默认关闭（需显式开启）。"""
    return get_bool("block_on_vpn", "GOOFISH_BLOCK_ON_VPN", default=False)
