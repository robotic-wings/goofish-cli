"""proxy_guard —— 开着 Clash/VPN 时的防呆拦截。

lru_cache 要点：detect_clash / config._load_file 都带缓存，测试里改环境后需清缓存。
"""
import pytest

from goofish_cli.core import config, proxy_guard
from goofish_cli.core.errors import ProxyBlockedError


@pytest.fixture(autouse=True)
def _clear_caches():
    proxy_guard.detect_clash.cache_clear()
    config._load_file.cache_clear()
    yield
    proxy_guard.detect_clash.cache_clear()
    config._load_file.cache_clear()


def _isolate_env(monkeypatch):
    for var in ("all_proxy", "https_proxy", "http_proxy",
                "ALL_PROXY", "HTTPS_PROXY", "HTTP_PROXY", "GOOFISH_BLOCK_ON_VPN"):
        monkeypatch.delenv(var, raising=False)


def test_env_proxy_to_loopback_is_detected(monkeypatch):
    _isolate_env(monkeypatch)
    monkeypatch.setenv("https_proxy", "http://127.0.0.1:7890")
    detected, reason = proxy_guard.detect_clash()
    assert detected and "127.0.0.1" in reason


def test_env_proxy_to_remote_not_detected(monkeypatch, tmp_path):
    _isolate_env(monkeypatch)
    # 指向远端（非回环）的公司代理不算 Clash 本地代理
    monkeypatch.setenv("https_proxy", "http://proxy.corp.example.com:8080")
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "none.json")
    # 其余系统探针在 CI 上一般为空；只断言 env 探针本身不误报
    assert proxy_guard._check_env_proxy() is None


def test_preflight_noop_when_disabled(monkeypatch):
    _isolate_env(monkeypatch)
    monkeypatch.setenv("https_proxy", "http://127.0.0.1:7890")
    monkeypatch.setenv("GOOFISH_BLOCK_ON_VPN", "0")
    proxy_guard.preflight()  # 关着开关：即便检测到代理也不拦


def test_preflight_raises_when_enabled_and_detected(monkeypatch):
    _isolate_env(monkeypatch)
    monkeypatch.setenv("https_proxy", "http://127.0.0.1:7890")
    monkeypatch.setenv("GOOFISH_BLOCK_ON_VPN", "1")
    with pytest.raises(ProxyBlockedError):
        proxy_guard.preflight()


def test_config_file_enables_block(monkeypatch, tmp_path):
    _isolate_env(monkeypatch)
    cfg = tmp_path / "config.json"
    cfg.write_text('{"block_on_vpn": true}')
    monkeypatch.setattr(config, "CONFIG_PATH", cfg)
    assert config.block_on_vpn() is True


def test_env_overrides_config_file(monkeypatch, tmp_path):
    _isolate_env(monkeypatch)
    cfg = tmp_path / "config.json"
    cfg.write_text('{"block_on_vpn": true}')
    monkeypatch.setattr(config, "CONFIG_PATH", cfg)
    monkeypatch.setenv("GOOFISH_BLOCK_ON_VPN", "0")
    assert config.block_on_vpn() is False


def test_host_parsing_variants():
    assert proxy_guard._host_of("http://127.0.0.1:7890") == "127.0.0.1"
    assert proxy_guard._host_of("socks5://user:pass@localhost:7891") == "localhost"
    assert proxy_guard._host_of("proxy.example.com:8080") == "proxy.example.com"


# --- 跨平台分发（不依赖真机 OS，靠 monkeypatch 平台标志）---

def test_system_proxy_dispatch_macos(monkeypatch):
    monkeypatch.setattr(proxy_guard, "IS_MACOS", True)
    monkeypatch.setattr(proxy_guard, "IS_WINDOWS", False)
    monkeypatch.setattr(proxy_guard, "_check_macos_system_proxy", lambda: "MAC_HIT")
    monkeypatch.setattr(proxy_guard, "_check_windows_system_proxy", lambda: "WIN_HIT")
    assert proxy_guard._check_system_proxy() == "MAC_HIT"


def test_system_proxy_dispatch_windows(monkeypatch):
    monkeypatch.setattr(proxy_guard, "IS_MACOS", False)
    monkeypatch.setattr(proxy_guard, "IS_WINDOWS", True)
    monkeypatch.setattr(proxy_guard, "_check_macos_system_proxy", lambda: "MAC_HIT")
    monkeypatch.setattr(proxy_guard, "_check_windows_system_proxy", lambda: "WIN_HIT")
    assert proxy_guard._check_system_proxy() == "WIN_HIT"


def test_system_proxy_dispatch_linux(monkeypatch):
    monkeypatch.setattr(proxy_guard, "IS_MACOS", False)
    monkeypatch.setattr(proxy_guard, "IS_WINDOWS", False)
    assert proxy_guard._check_system_proxy() is None


def test_process_check_uses_tasklist_on_windows(monkeypatch):
    captured = {}

    def fake_run(cmd, **kw):
        captured["cmd"] = cmd

        class R:
            stdout = "clash-verge.exe\nchrome.exe\n"
        return R()

    monkeypatch.setattr(proxy_guard, "IS_WINDOWS", True)
    monkeypatch.setattr(proxy_guard.subprocess, "run", fake_run)
    reason = proxy_guard._check_clash_process()
    assert captured["cmd"] == ["tasklist"]
    assert "clash" in reason.lower()


def test_process_check_uses_ps_on_unix(monkeypatch):
    captured = {}

    def fake_run(cmd, **kw):
        captured["cmd"] = cmd

        class R:
            stdout = "chrome\nfinder\n"
        return R()

    monkeypatch.setattr(proxy_guard, "IS_WINDOWS", False)
    monkeypatch.setattr(proxy_guard.subprocess, "run", fake_run)
    assert proxy_guard._check_clash_process() is None
    assert captured["cmd"] == ["ps", "-Ao", "comm="]
