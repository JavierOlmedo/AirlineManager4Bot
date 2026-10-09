"""Launch a profile in its own window and give it a desktop shortcut (Windows)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import paths

ROOT = Path(__file__).resolve().parents[1]


def window_python() -> Path:
    """pythonw.exe next to the running interpreter (no console window), else the interpreter itself."""
    current = Path(sys.executable)
    candidate = current.with_name("pythonw.exe")
    return candidate if os.name == "nt" and candidate.exists() else current


def profile_args(profile: paths.Profile) -> list[str]:
    return ["src\\main.py" if os.name == "nt" else "src/main.py"] + ([] if profile.is_main else ["--profile", profile.name])


def launch(profile: paths.Profile) -> None:
    """Open the desktop window of *profile* as a separate program."""
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen([str(window_python())] + profile_args(profile), cwd=ROOT, creationflags=flags, close_fds=True)


def create_desktop_shortcut(profile: paths.Profile) -> Optional[str]:
    """'AM4 Bot (<profile>).lnk' on the desktop, like the main shortcut. Returns its name, None if not possible."""
    if os.name != "nt":
        return None
    name = "Airline Manager 4 Bot.lnk" if profile.is_main else f"AM4 Bot ({profile.label}).lnk"
    env = dict(os.environ, AM4_LNK=name, AM4_TARGET=str(window_python()), AM4_ARGS=" ".join(profile_args(profile)),
               AM4_DIR=str(ROOT), AM4_ICON=str(ROOT / "assets" / "favicon.ico"),
               AM4_DESC=f"Airline Manager 4 Bot - perfil {profile.label}")
    script = ("$s = New-Object -ComObject WScript.Shell; "
              "$l = $s.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) $env:AM4_LNK)); "
              "$l.TargetPath = $env:AM4_TARGET; $l.Arguments = $env:AM4_ARGS; $l.WorkingDirectory = $env:AM4_DIR; "
              "$l.IconLocation = $env:AM4_ICON + ',0'; $l.Description = $env:AM4_DESC; $l.Save()")
    try:
        result = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script], env=env,
                                capture_output=True, timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return None
    return name if result.returncode == 0 else None
