"""execjs 桥接 goofish_js_version_2.js。提供 sign/device_id/mid/uuid/decrypt。"""
from __future__ import annotations

import subprocess
from functools import lru_cache
from importlib.resources import files

# execjs（跑 node）和 browser_cookie3 的子进程输出在中文 Windows 上是 GBK/cp936，
# Python 默认按 locale 解、execjs 又常按 utf-8 解，遇到 0xD2 这类字节会在读取线程里
# 抛 UnicodeDecodeError（表现为 PytestUnhandledThreadExceptionWarning）。
# 统一给 Popen 补上 encoding=utf-8 + errors=replace 的**默认值**：用 setdefault 而非
# partial，避免和显式传了 encoding/errors 的调用方（如 proxy_guard 的 errors="ignore"）
# 撞成 "multiple values for keyword argument"。
_ORIG_POPEN = subprocess.Popen


def _popen_utf8_lenient(*args, **kwargs):
    kwargs.setdefault("encoding", "utf-8")
    kwargs.setdefault("errors", "replace")
    return _ORIG_POPEN(*args, **kwargs)


subprocess.Popen = _popen_utf8_lenient

import execjs  # noqa: E402  必须在 subprocess 补丁之后


@lru_cache(maxsize=1)
def _ctx() -> execjs._abstract_runtime.AbstractRuntimeContext:
    js_path = files("goofish_cli.static").joinpath("goofish_js_version_2.js")
    return execjs.compile(js_path.read_text(encoding="utf-8"))


def generate_sign(t: str, token: str, data: str) -> str:
    return _ctx().call("generate_sign", t, token, data)


def generate_device_id(user_id: str) -> str:
    return _ctx().call("generate_device_id", user_id)


def generate_mid() -> str:
    return _ctx().call("generate_mid")


def generate_uuid() -> str:
    return _ctx().call("generate_uuid")


def decrypt(data: str) -> str:
    return _ctx().call("decrypt", data)
