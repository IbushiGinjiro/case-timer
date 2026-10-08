"""配布用のビルド：exe（PyInstaller）→ インストーラー（Inno Setup）。

    python build.py

出力：dist/case-timer/（exe一式）、release/case-timer-setup-<版>.exe
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

from app import __version__

ROOT = Path(__file__).resolve().parent


def iscc() -> str:
    for p in [Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Inno Setup 6/ISCC.exe",
              Path(os.environ.get("ProgramFiles(x86)", "")) / "Inno Setup 6/ISCC.exe",
              Path(os.environ.get("ProgramFiles", "")) / "Inno Setup 6/ISCC.exe"]:
        if p.is_file():
            return str(p)
    found = shutil.which("ISCC")
    if found:
        return found
    sys.exit("Inno Setup 6 が見つかりません（winget install JRSoftware.InnoSetup）")


def main():
    iss = (ROOT / "installer/case-timer.iss").read_text(encoding="utf-8")
    ver = (ROOT / "installer/version_info.txt").read_text(encoding="utf-8")
    if f'#define AppVersion "{__version__}"' not in iss or f"'ProductVersion', '{__version__}'" not in ver:
        sys.exit(f"バージョンがそろっていません（app/__init__.py は {__version__}）")
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
                    "--name", "case-timer", "--icon", "assets/case-timer.ico",
                    "--version-file", "installer/version_info.txt",
                    "--add-data", "web;web", "run.py"], cwd=ROOT, check=True)
    subprocess.run([iscc(), "/Qp", "installer/case-timer.iss"], cwd=ROOT, check=True)
    print("done:", ROOT / "release" / f"case-timer-setup-{__version__}.exe")


if __name__ == "__main__":
    main()
