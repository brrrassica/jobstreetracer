"""Local setup helpers: bridge readiness, feed discovery and autostart.

These helpers are used by the CLI (`jobstreetracer setup`) and the localhost
bridge API so the PWA can offer one-click autostart when the bridge is running.
They only touch the current user's environment unless a privileged boot-level
install is explicitly requested.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

APP_NAME = "JobStreetracer Bridge"
LINUX_DESKTOP_ID = "jobstreetracer-bridge.desktop"
LINUX_USER_UNIT = "jobstreetracer-bridge.service"
WINDOWS_TASK = "JobStreetracer Bridge"
MACOS_PLIST = "com.jobstreetracer.bridge.plist"


@dataclass
class AutostartState:
    supported: bool
    enabled: bool
    method: str
    path: str = ""
    command: str = ""
    detail: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def package_root() -> Path:
    # src/jobstreetracer/setup.py -> repo root
    return Path(__file__).resolve().parents[2]


def detect_static_dir(root: Path | None = None) -> Path | None:
    root = (root or package_root()).resolve()
    candidates = [root / "web" / "dist", root / "dist", root / "docs" / "pwa"]
    for candidate in candidates:
        if (candidate / "index.html").is_file():
            return candidate
    return None


def detect_config_path(root: Path | None = None) -> Path | None:
    root = (root or package_root()).resolve()
    candidates = [root / "config.toml"]
    env = os.environ.get("JOBSTREETRACER_CONFIG")
    if env:
        candidates.insert(0, Path(env).expanduser())
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return None


def resolve_bridge_command(
    *,
    root: Path | None = None,
    host: str = "127.0.0.1",
    port: int = 8765,
    config_path: Path | None = None,
    static_dir: Path | None = None,
) -> list[str]:
    root = (root or package_root()).resolve()
    python = Path(sys.executable)
    if not python.exists():  # pragma: no cover - defensive
        python = Path(sys.executable or "python3")
    cmd = [str(python), "-m", "jobstreetracer.bridge", "--host", host, "--port", str(port)]
    config = config_path or detect_config_path(root)
    if config:
        cmd.extend(["--config", str(config)])
    static = static_dir or detect_static_dir(root)
    if static:
        cmd.extend(["--static", str(static)])
    return cmd


def command_string(cmd: list[str]) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline(cmd)
    return shlex.join(cmd)


def _linux_desktop_path() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "autostart" / LINUX_DESKTOP_ID


def _linux_user_unit_path() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "systemd" / "user" / LINUX_USER_UNIT


def _windows_run_key() -> str:
    return r"Software\Microsoft\Windows\CurrentVersion\Run"


def _windows_task_script_path() -> Path:
    appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(appdata) / "JobStreetracer" / "bridge-autostart.cmd"


def _mac_launch_agents_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / MACOS_PLIST


def _run(
    args: list[str],
    *,
    check: bool = False,
    capture: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        check=check,
        text=True,
        capture_output=capture,
    )


def autostart_status(*, root: Path | None = None) -> AutostartState:
    root = (root or package_root()).resolve()
    if sys.platform.startswith("linux"):
        desktop = _linux_desktop_path()
        if desktop.is_file():
            return AutostartState(
                supported=True,
                enabled=True,
                method="linux-login",
                path=str(desktop),
                detail="Desktop autostart entry is present.",
            )
        unit = _linux_user_unit_path()
        if unit.is_file():
            enabled = False
            if shutil.which("systemctl"):
                probe = _run(["systemctl", "--user", "is-enabled", LINUX_USER_UNIT])
                enabled = probe.returncode == 0 and probe.stdout.strip() == "enabled"
            return AutostartState(
                supported=True,
                enabled=enabled,
                method="linux-user-service",
                path=str(unit),
                detail="systemd user service is installed.",
            )
        return AutostartState(
            supported=True,
            enabled=False,
            method="linux-login",
            detail="No autostart entry found.",
        )

    if os.name == "nt":
        try:
            import winreg  # type: ignore[attr-defined]

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _windows_run_key()) as key:
                try:
                    value, _ = winreg.QueryValueEx(key, APP_NAME)
                    return AutostartState(
                        supported=True,
                        enabled=True,
                        method="windows-login",
                        path=_windows_run_key(),
                        command=str(value),
                        detail="Registry Run entry is present.",
                    )
                except FileNotFoundError:
                    pass
        except Exception as exc:  # pragma: no cover - platform specific
            return AutostartState(
                supported=False,
                enabled=False,
                method="windows-login",
                error=str(exc),
                detail="Could not read Windows autostart state.",
            )
        return AutostartState(
            supported=True,
            enabled=False,
            method="windows-login",
            detail="No Windows autostart entry found.",
        )

    if sys.platform == "darwin":
        plist = _mac_launch_agents_path()
        return AutostartState(
            supported=True,
            enabled=plist.is_file(),
            method="macos-login",
            path=str(plist),
            detail="LaunchAgents plist is present." if plist.is_file() else "No LaunchAgents plist found.",
        )

    return AutostartState(
        supported=False,
        enabled=False,
        method="unknown",
        detail=f"Autostart setup is not automated on {sys.platform}.",
    )


def _write_linux_desktop(cmd: list[str]) -> Path:
    path = _linux_desktop_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    exec_line = command_string(cmd)
    content = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={APP_NAME}\n"
        "Comment=Localhost feed, refresh and Telegram relay for the JobStreetracer PWA\n"
        f"Exec={exec_line}\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n"
        "NoDisplay=true\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def _write_linux_user_service(cmd: list[str]) -> Path:
    path = _linux_user_unit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    exec_start = command_string(cmd)
    content = (
        "[Unit]\n"
        "Description=JobStreetracer localhost bridge\n"
        "After=network-online.target\n"
        "Wants=network-online.target\n\n"
        "[Service]\n"
        "Type=simple\n"
        f"ExecStart={exec_start}\n"
        "Restart=on-failure\n"
        "RestartSec=5\n\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )
    path.write_text(content, encoding="utf-8")
    if shutil.which("systemctl"):
        _run(["systemctl", "--user", "daemon-reload"])
        _run(["systemctl", "--user", "enable", "--now", LINUX_USER_UNIT])
    return path


def _write_windows_autostart(cmd: list[str]) -> Path:
    script = _windows_task_script_path()
    script.parent.mkdir(parents=True, exist_ok=True)
    root = package_root()
    lines = [
        "@echo off",
        f'cd /d "{root}"',
        f'start "" /min {subprocess.list2cmdline(cmd)}',
        "",
    ]
    script.write_text("\r\n".join(lines), encoding="utf-8")
    import winreg  # type: ignore[attr-defined]

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _windows_run_key()) as key:
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, f'"{script}"')
    return script


def _write_macos_launch_agent(cmd: list[str]) -> Path:
    plist = _mac_launch_agents_path()
    plist.parent.mkdir(parents=True, exist_ok=True)
    args_xml = "".join(f"      <string>{part}</string>\n" for part in cmd)
    content = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n<dict>\n'
        f"  <key>Label</key><string>{MACOS_PLIST}</string>\n"
        "  <key>ProgramArguments</key>\n  <array>\n"
        f"{args_xml}  </array>\n"
        "  <key>RunAtLoad</key><true/>\n"
        "  <key>KeepAlive</key><true/>\n"
        "</dict>\n</plist>\n"
    )
    plist.write_text(content, encoding="utf-8")
    return plist


def enable_autostart(
    *,
    root: Path | None = None,
    host: str = "127.0.0.1",
    port: int = 8765,
    config_path: Path | None = None,
    static_dir: Path | None = None,
    method: str = "auto",
) -> AutostartState:
    root = (root or package_root()).resolve()
    cmd = resolve_bridge_command(
        root=root, host=host, port=port, config_path=config_path, static_dir=static_dir
    )
    if sys.platform.startswith("linux"):
        chosen = method if method in {"linux-login", "linux-user-service"} else "linux-login"
        try:
            if chosen == "linux-user-service":
                path = _write_linux_user_service(cmd)
            else:
                path = _write_linux_desktop(cmd)
            state = autostart_status(root=root)
            state.command = command_string(cmd)
            state.path = str(path)
            state.method = chosen
            state.enabled = True
            state.detail = f"Autostart enabled via {chosen}."
            return state
        except Exception as exc:
            return AutostartState(
                supported=True,
                enabled=False,
                method=chosen,
                command=command_string(cmd),
                error=str(exc),
                detail="Failed to enable autostart.",
            )

    if os.name == "nt":
        try:
            path = _write_windows_autostart(cmd)
            return AutostartState(
                supported=True,
                enabled=True,
                method="windows-login",
                path=str(path),
                command=command_string(cmd),
                detail="Autostart enabled via the current user's Run key.",
            )
        except Exception as exc:
            return AutostartState(
                supported=True,
                enabled=False,
                method="windows-login",
                command=command_string(cmd),
                error=str(exc),
                detail="Failed to enable Windows autostart.",
            )

    if sys.platform == "darwin":
        try:
            path = _write_macos_launch_agent(cmd)
            return AutostartState(
                supported=True,
                enabled=True,
                method="macos-login",
                path=str(path),
                command=command_string(cmd),
                detail="LaunchAgent plist written (load with launchctl to start immediately).",
            )
        except Exception as exc:
            return AutostartState(
                supported=True,
                enabled=False,
                method="macos-login",
                command=command_string(cmd),
                error=str(exc),
                detail="Failed to enable macOS autostart.",
            )

    return AutostartState(
        supported=False,
        enabled=False,
        method="unknown",
        command=command_string(cmd),
        detail=f"Autostart setup is not automated on {sys.platform}.",
    )


def disable_autostart(*, root: Path | None = None) -> AutostartState:
    root = (root or package_root()).resolve()
    errors: list[str] = []
    if sys.platform.startswith("linux"):
        desktop = _linux_desktop_path()
        if desktop.exists():
            try:
                desktop.unlink()
            except Exception as exc:
                errors.append(str(exc))
        unit = _linux_user_unit_path()
        if shutil.which("systemctl"):
            _run(["systemctl", "--user", "disable", "--now", LINUX_USER_UNIT])
        if unit.exists():
            try:
                unit.unlink()
                if shutil.which("systemctl"):
                    _run(["systemctl", "--user", "daemon-reload"])
            except Exception as exc:
                errors.append(str(exc))
        state = autostart_status(root=root)
        if errors:
            state.error = "; ".join(errors)
            state.detail = "Tried to remove autostart entries, but some operations failed."
        else:
            state.detail = "Autostart disabled."
        return state

    if os.name == "nt":
        try:
            import winreg  # type: ignore[attr-defined]

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, _windows_run_key(), 0, winreg.KEY_SET_VALUE
            ) as key:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass
        except Exception as exc:
            errors.append(str(exc))
        script = _windows_task_script_path()
        if script.exists():
            try:
                script.unlink()
            except Exception as exc:
                errors.append(str(exc))
        state = autostart_status(root=root)
        if errors:
            state.error = "; ".join(errors)
        else:
            state.detail = "Windows autostart disabled."
        return state

    if sys.platform == "darwin":
        plist = _mac_launch_agents_path()
        if plist.exists():
            try:
                plist.unlink()
            except Exception as exc:
                errors.append(str(exc))
        state = autostart_status(root=root)
        if errors:
            state.error = "; ".join(errors)
        else:
            state.detail = "macOS LaunchAgent removed."
        return state

    return AutostartState(
        supported=False,
        enabled=False,
        method="unknown",
        detail=f"Autostart setup is not automated on {sys.platform}.",
    )


def setup_status(*, root: Path | None = None, host: str = "127.0.0.1", port: int = 8765) -> dict[str, Any]:
    root = (root or package_root()).resolve()
    static_dir = detect_static_dir(root)
    config_path = detect_config_path(root)
    cmd = resolve_bridge_command(root=root, host=host, port=port, config_path=config_path, static_dir=static_dir)
    return {
        "root": str(root),
        "python": sys.executable,
        "platform": sys.platform,
        "static_dir": str(static_dir) if static_dir else "",
        "config_path": str(config_path) if config_path else "",
        "feed_url": f"http://{host}:{port}/api/feed",
        "bridge_url": f"http://{host}:{port}",
        "pwa_url": f"http://{host}:{port}/jobstreetracer/" if static_dir else "https://brrrassica.github.io/jobstreetracer/",
        "command": cmd,
        "command_string": command_string(cmd),
        "autostart": autostart_status(root=root).to_dict(),
    }


def install_command_text(*, root: Path | None = None) -> str:
    root = (root or package_root()).resolve()
    if os.name == "nt":
        return (
            f'cd /d "{root}"\r\n'
            "python -m venv .venv\r\n"
            ".venv\\Scripts\\pip install -e .\r\n"
            ".venv\\Scripts\\jobstreetracer setup --enable-autostart\r\n"
            ".venv\\Scripts\\jobstreetracer bridge --static web\\dist --open\r\n"
        )
    return (
        f'cd "{root}"\n'
        "python3 -m venv .venv\n"
        ".venv/bin/pip install -e .\n"
        ".venv/bin/jobstreetracer setup --enable-autostart\n"
        ".venv/bin/jobstreetracer bridge --static web/dist --open\n"
    )
