from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from jobstreetracer import setup


@pytest.fixture
def linux_env(tmp_path: Path, monkeypatch):
    """Force the Linux code path with an isolated XDG_CONFIG_HOME and no systemctl."""
    xdg = tmp_path / "config"
    xdg.mkdir()
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    # Pretend systemctl is not installed so nothing shells out to a real init system.
    monkeypatch.setattr(setup.shutil, "which", lambda name: None)
    return xdg


# --------------------------------------------------------------------------
# Detection helpers
# --------------------------------------------------------------------------
def test_package_root_contains_src() -> None:
    root = setup.package_root()
    assert (root / "src" / "jobstreetracer").is_dir()


def test_detect_static_dir_finds_web_dist(tmp_path: Path) -> None:
    dist = tmp_path / "web" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("<html></html>", encoding="utf-8")
    assert setup.detect_static_dir(root=tmp_path) == dist.resolve()


def test_detect_static_dir_prefers_web_dist_over_root_dist(tmp_path: Path) -> None:
    for name in ("web/dist", "dist"):
        d = tmp_path / name
        d.mkdir(parents=True)
        (d / "index.html").write_text("<html></html>", encoding="utf-8")
    assert setup.detect_static_dir(root=tmp_path) == (tmp_path / "web" / "dist").resolve()


def test_detect_static_dir_missing_returns_none(tmp_path: Path) -> None:
    assert setup.detect_static_dir(root=tmp_path) is None


def test_detect_config_path_plain(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("JOBSTREETRACER_CONFIG", raising=False)
    cfg = tmp_path / "config.toml"
    cfg.write_text("[app]\n", encoding="utf-8")
    assert setup.detect_config_path(root=tmp_path) == cfg.resolve()


def test_detect_config_path_env_takes_precedence(tmp_path: Path, monkeypatch) -> None:
    local = tmp_path / "config.toml"
    local.write_text("[app]\n", encoding="utf-8")
    env_cfg = tmp_path / "elsewhere.toml"
    env_cfg.write_text("[app]\n", encoding="utf-8")
    monkeypatch.setenv("JOBSTREETRACER_CONFIG", str(env_cfg))
    assert setup.detect_config_path(root=tmp_path) == env_cfg.resolve()


def test_detect_config_path_env_missing_falls_back(tmp_path: Path, monkeypatch) -> None:
    local = tmp_path / "config.toml"
    local.write_text("[app]\n", encoding="utf-8")
    monkeypatch.setenv("JOBSTREETRACER_CONFIG", str(tmp_path / "gone.toml"))
    assert setup.detect_config_path(root=tmp_path) == local.resolve()


def test_detect_config_path_none(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("JOBSTREETRACER_CONFIG", raising=False)
    assert setup.detect_config_path(root=tmp_path) is None


# --------------------------------------------------------------------------
# Command composition
# --------------------------------------------------------------------------
def test_resolve_bridge_command_minimal(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("JOBSTREETRACER_CONFIG", raising=False)
    cmd = setup.resolve_bridge_command(root=tmp_path, host="127.0.0.1", port=9000)
    assert cmd[:2] == [sys.executable, "-m"]
    assert cmd[2:5] == ["jobstreetracer.bridge", "--host", "127.0.0.1"]
    assert cmd[5:7] == ["--port", "9000"]
    assert "--config" not in cmd
    assert "--static" not in cmd


def test_resolve_bridge_command_includes_detected_paths(tmp_path: Path) -> None:
    cfg = tmp_path / "config.toml"
    cfg.write_text("[app]\n", encoding="utf-8")
    dist = tmp_path / "web" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("<html></html>", encoding="utf-8")

    cmd = setup.resolve_bridge_command(root=tmp_path)

    assert cmd[cmd.index("--config") + 1] == str(cfg.resolve())
    assert cmd[cmd.index("--static") + 1] == str(dist.resolve())


def test_resolve_bridge_command_explicit_overrides(tmp_path: Path) -> None:
    config_path = tmp_path / "custom.toml"
    static_dir = tmp_path / "static"
    cmd = setup.resolve_bridge_command(
        root=tmp_path, config_path=config_path, static_dir=static_dir
    )
    assert cmd[cmd.index("--config") + 1] == str(config_path)
    assert cmd[cmd.index("--static") + 1] == str(static_dir)


def test_command_string_posix_quoting(monkeypatch) -> None:
    monkeypatch.setattr(os, "name", "posix")
    cmd = ["python3", "-m", "pkg", "--msg", "a b"]
    assert setup.command_string(cmd) == "python3 -m pkg --msg 'a b'"


# --------------------------------------------------------------------------
# Autostart state machine (linux-login via .desktop)
# --------------------------------------------------------------------------
def test_autostart_status_disabled_by_default(linux_env: Path) -> None:
    state = setup.autostart_status()
    assert state.supported is True
    assert state.enabled is False
    assert state.method == "linux-login"
    assert state.error == ""


def test_enable_disable_autostart_roundtrip(linux_env: Path, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("JOBSTREETRACER_CONFIG", raising=False)
    state = setup.enable_autostart(root=tmp_path, host="127.0.0.1", port=8765)
    assert state.enabled is True
    assert state.method == "linux-login"

    desktop = linux_env / "autostart" / setup.LINUX_DESKTOP_ID
    assert desktop.is_file()
    content = desktop.read_text(encoding="utf-8")
    assert "[Desktop Entry]" in content
    assert setup.APP_NAME in content
    assert "Exec=" in content

    status = setup.autostart_status()
    assert status.enabled is True
    assert status.path == str(desktop)

    disabled = setup.disable_autostart()
    assert disabled.enabled is False
    assert not desktop.exists()


def test_enable_autostart_method_override(linux_env: Path, tmp_path: Path) -> None:
    # An unknown method name falls back to linux-login.
    state = setup.enable_autostart(root=tmp_path, method="bogus")
    assert state.method == "linux-login"
    assert (linux_env / "autostart" / setup.LINUX_DESKTOP_ID).is_file()


def test_enable_autostart_user_service_writes_unit(linux_env: Path, tmp_path: Path) -> None:
    state = setup.enable_autostart(root=tmp_path, method="linux-user-service")
    assert state.enabled is True
    assert state.method == "linux-user-service"

    unit = linux_env / "systemd" / "user" / setup.LINUX_USER_UNIT
    assert unit.is_file()
    content = unit.read_text(encoding="utf-8")
    assert "[Service]" in content
    assert "ExecStart=" in content

    # Status should report the unit's presence, and disable should remove it.
    status = setup.autostart_status()
    assert status.enabled is False  # systemctl unavailable => cannot confirm enabled
    assert status.method == "linux-user-service"
    assert status.detail == "systemd user service is installed."

    disabled = setup.disable_autostart()
    assert disabled.enabled is False
    assert not unit.exists()


def test_enable_autostart_reports_write_failure(linux_env: Path, tmp_path: Path, monkeypatch) -> None:
    def boom(cmd: list[str]) -> Path:
        raise OSError("disk on fire")

    monkeypatch.setattr(setup, "_write_linux_desktop", boom)
    state = setup.enable_autostart(root=tmp_path)
    assert state.enabled is False
    assert "disk on fire" in state.error
    assert state.detail == "Failed to enable autostart."


def test_disable_autostart_is_idempotent(linux_env: Path, tmp_path: Path) -> None:
    state = setup.disable_autostart(root=tmp_path)
    assert state.supported is True
    assert state.enabled is False


# --------------------------------------------------------------------------
# macOS code path (fake HOME)
# --------------------------------------------------------------------------
def test_macos_autostart_roundtrip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    state = setup.enable_autostart(root=tmp_path)
    assert state.enabled is True
    assert state.method == "macos-login"

    plist = tmp_path / "Library" / "LaunchAgents" / setup.MACOS_PLIST
    assert plist.is_file()
    assert "<key>RunAtLoad</key>" in plist.read_text(encoding="utf-8")

    assert setup.autostart_status().enabled is True

    setup.disable_autostart()
    assert not plist.exists()
    assert setup.autostart_status().enabled is False


# --------------------------------------------------------------------------
# Unknown platform
# --------------------------------------------------------------------------
def test_unknown_platform_unsupported(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(sys, "platform", "plan9")
    monkeypatch.setattr(os, "name", "plan9")
    status = setup.autostart_status(root=tmp_path)
    assert status.supported is False
    assert status.enabled is False
    assert status.method == "unknown"

    enabled = setup.enable_autostart(root=tmp_path)
    assert enabled.supported is False

    disabled = setup.disable_autostart(root=tmp_path)
    assert disabled.supported is False


# --------------------------------------------------------------------------
# setup_status aggregate
# --------------------------------------------------------------------------
def test_setup_status_reports_discovered_state(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("JOBSTREETRACER_CONFIG", raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(setup.shutil, "which", lambda name: None)

    cfg = tmp_path / "config.toml"
    cfg.write_text("[app]\n", encoding="utf-8")
    dist = tmp_path / "web" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("<html></html>", encoding="utf-8")

    info = setup.setup_status(root=tmp_path, host="127.0.0.1", port=8765)

    assert info["config_path"] == str(cfg.resolve())
    assert info["static_dir"] == str(dist.resolve())
    assert info["feed_url"] == "http://127.0.0.1:8765/api/feed"
    assert info["pwa_url"] == "http://127.0.0.1:8765/jobstreetracer/"
    assert info["autostart"]["enabled"] is False
    assert info["command_string"].startswith(sys.executable)


def test_setup_status_falls_back_to_github_pages(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("JOBSTREETRACER_CONFIG", raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    info = setup.setup_status(root=tmp_path)
    assert info["static_dir"] == ""
    assert info["config_path"] == ""
    assert info["pwa_url"] == "https://brrrassica.github.io/jobstreetracer/"


# --------------------------------------------------------------------------
# Install help text
# --------------------------------------------------------------------------
def test_install_command_text_posix(monkeypatch) -> None:
    monkeypatch.setattr(os, "name", "posix")
    text = setup.install_command_text(root=Path("/opt/app"))
    assert 'cd "/opt/app"' in text
    assert ".venv/bin/pip install -e ." in text
    assert "--enable-autostart" in text


def test_install_command_text_windows(monkeypatch, tmp_path: Path) -> None:
    # os.name is patched but the Path itself stays a posix path so resolve()
    # works; the windows branch only emits static command text anyway.
    monkeypatch.setattr(os, "name", "nt")
    text = setup.install_command_text(root=tmp_path)
    assert f'cd /d "{tmp_path.resolve()}"' in text
    assert "\r\n" in text
    assert ".venv\\Scripts\\pip install -e ." in text
    assert "--enable-autostart" in text
