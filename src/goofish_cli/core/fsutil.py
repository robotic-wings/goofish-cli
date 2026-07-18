"""跨平台文件工具。

restrict_to_owner：把敏感文件（cookies / device 缓存）权限收紧到仅属主可访问。
- POSIX（mac/linux）：chmod 0o600。
- Windows：NTFS 不认 Unix mode 位，改用 icacls 去掉继承 + 只授当前用户完全控制；
  best-effort，失败不致命——文件内容本身已加密，且 %USERPROFILE% 默认只有本人 +
  管理员可访问。
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from loguru import logger

IS_WINDOWS = os.name == "nt"


def restrict_to_owner(path: Path) -> None:
    """收紧文件权限到仅属主可读写。跨平台，Windows 上 best-effort。"""
    if IS_WINDOWS:
        _restrict_windows(path)
    else:
        path.chmod(0o600)


def _restrict_windows(path: Path) -> None:
    # os.chmod 在 Windows 上只认只读位，无法表达"仅属主"，只能走 icacls。
    user = os.environ.get("USERNAME")
    if not user:
        logger.debug("restrict_to_owner: 无 USERNAME，跳过 Windows ACL 收紧")
        return
    try:
        subprocess.run(
            ["icacls", str(path), "/inheritance:r", "/grant:r", f"{user}:F"],
            capture_output=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as e:
        logger.debug(f"restrict_to_owner: icacls 失败（忽略）：{e}")
