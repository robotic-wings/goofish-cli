"""防呆：检测系统是否在走 Clash 类代理 / VPN。

为什么要拦：闲鱼风控对出口 IP 很敏感，开着代理访问容易登录失败甚至触发风控。
开启 block_on_vpn 后，检测到代理就在真正发请求前拒绝执行，避免把好账号打进小黑屋。

检测尽量"宁可漏报不误伤"，但因为是用户显式开启的防呆，容忍一定灵敏度；命中时
错误信息会告诉用户怎么临时绕过（关代理，或 GOOFISH_BLOCK_ON_VPN=0 单次跳过）。

检测信号（任一命中即判定）：
1. 环境变量 http(s)_proxy / all_proxy 指向本机回环地址；
2. macOS 系统代理（scutil --proxy）开启且指向 127.0.0.1；
3. 运行中的 Clash 家族进程（clash / mihomo / clashx / clash verge …）；
4. Clash 默认 external-controller 端口（9090）在本机监听。
结果按进程生命周期缓存——一条命令执行期间代理状态不会变。
"""
from __future__ import annotations

import os
import socket
import subprocess
from functools import lru_cache

from loguru import logger

from goofish_cli.core.config import block_on_vpn
from goofish_cli.core.errors import ProxyBlockedError

# Clash 家族常用本地端口（混合/HTTP/SOCKS）+ 控制端口
_CLASH_PROXY_PORTS = {7890, 7891, 7892, 7893, 7897, 7078}
_CLASH_CTRL_PORT = 9090
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "0.0.0.0"}
# 进程名关键字（小写子串匹配）
_CLASH_PROC_HINTS = ("clash", "mihomo", "clashx", "verge-mihomo")
_PROXY_ENV_VARS = ("all_proxy", "https_proxy", "http_proxy")


def _host_of(value: str) -> str:
    """从 proxy 值里抠出 host。支持 http://h:p、h:p、socks5://h:p。"""
    v = value.split("://", 1)[-1]
    v = v.rsplit("@", 1)[-1]  # 去掉 user:pass@
    host = v.rsplit(":", 1)[0] if ":" in v else v
    return host.strip("[]").strip().lower()


def _check_env_proxy() -> str | None:
    for var in _PROXY_ENV_VARS:
        val = os.environ.get(var) or os.environ.get(var.upper())
        if val and _host_of(val) in _LOOPBACK_HOSTS:
            return f"环境变量 {var}={val} 指向本机代理"
    return None


def _check_macos_system_proxy() -> str | None:
    try:
        out = subprocess.run(
            ["scutil", "--proxy"], capture_output=True, text=True, timeout=2
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    cfg: dict[str, str] = {}
    for line in out.splitlines():
        if ":" in line:
            k, _, v = line.strip().partition(":")
            cfg[k.strip()] = v.strip()
    for proto, host_key in (("HTTP", "HTTPProxy"), ("HTTPS", "HTTPSProxy"), ("SOCKS", "SOCKSProxy")):
        if cfg.get(f"{proto}Enable") == "1" and cfg.get(host_key, "").lower() in _LOOPBACK_HOSTS:
            port = cfg.get(f"{proto}Port", "")
            return f"系统{proto}代理已开启 → {cfg.get(host_key)}:{port}"
    return None


def _check_clash_process() -> str | None:
    try:
        out = subprocess.run(
            ["ps", "-Ao", "comm="], capture_output=True, text=True, timeout=2
        ).stdout.lower()
    except (OSError, subprocess.SubprocessError):
        return None
    for hint in _CLASH_PROC_HINTS:
        if hint in out:
            return f"检测到运行中的 Clash 类进程（{hint}）"
    return None


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.2)
        try:
            return s.connect_ex(("127.0.0.1", port)) == 0
        except OSError:
            return False


def _check_clash_ctrl_port() -> str | None:
    if _port_open(_CLASH_CTRL_PORT):
        return f"Clash 控制端口 127.0.0.1:{_CLASH_CTRL_PORT} 在监听"
    return None


@lru_cache(maxsize=1)
def detect_clash() -> tuple[bool, str]:
    """返回 (是否检测到 Clash 类代理, 命中原因)。检测本身出错时按"未检测到"处理（fail-open）。"""
    for probe in (
        _check_env_proxy,
        _check_macos_system_proxy,
        _check_clash_process,
        _check_clash_ctrl_port,
    ):
        try:
            reason = probe()
        except Exception as e:  # noqa: BLE001 检测不该拖垮主流程
            logger.debug(f"proxy_guard probe {probe.__name__} 异常：{e}")
            continue
        if reason:
            return True, reason
    return False, ""


def preflight() -> None:
    """在真正访问闲鱼前调用。block_on_vpn 开启且检测到代理时抛 ProxyBlockedError。"""
    if not block_on_vpn():
        return
    detected, reason = detect_clash()
    if detected:
        raise ProxyBlockedError(
            f"检测到系统正在使用 Clash 类代理 / VPN（{reason}），已按 block_on_vpn 配置拒绝执行。\n"
            "开着代理访问闲鱼容易登录失败甚至触发风控。请先关闭代理后重试；\n"
            "确需本次跳过检测：`GOOFISH_BLOCK_ON_VPN=0 goofish ...`，\n"
            "永久关闭：把 ~/.goofish-cli/config.json 的 block_on_vpn 改为 false。"
        )
