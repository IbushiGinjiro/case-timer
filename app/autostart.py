"""Windowsのスタートアップ登録（HKCU の Run キー）。管理者権限は不要。"""
import sys
import winreg
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "case-timer"


def command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    # 開発時は pythonw（コンソールを出さない）で run.py を起動する
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    run_py = Path(__file__).resolve().parent.parent / "run.py"
    return f'"{pythonw}" "{run_py}"'


def registered() -> str | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            return winreg.QueryValueEx(k, VALUE_NAME)[0]
    except OSError:
        return None


def is_enabled() -> bool:
    return registered() is not None


def set_enabled(on: bool):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, VALUE_NAME, 0, winreg.REG_SZ, command())
        else:
            try:
                winreg.DeleteValue(k, VALUE_NAME)
            except FileNotFoundError:
                pass
