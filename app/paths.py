"""ファイルの置き場所。

- ソース・画面（web/）: このリポジトリ（exe化した場合は同梱）
- 起動用の設定（記録データの保存先だけを書く）: %APPDATA%\\case-timer\\config.json
- 記録DB: ユーザーが選んだフォルダ（既定は OneDrive のドキュメント配下）
"""
import json
import os
import sys
from pathlib import Path

APP_NAME = "case-timer"
DB_FILENAME = "case-timer.db"


def resource_dir() -> Path:
    # PyInstaller でexe化したときは __file__ が一時フォルダを指すので _MEIPASS を使う
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


WEB_DIR = resource_dir() / "web"


def boot_config_path() -> Path:
    base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    return base / APP_NAME / "config.json"


def documents_dir() -> Path:
    onedrive = os.environ.get("OneDrive")
    candidates = []
    if onedrive:
        candidates += [Path(onedrive) / "ドキュメント", Path(onedrive) / "Documents"]
    candidates += [Path.home() / "Documents"]
    for c in candidates:
        if c.is_dir():
            return c
    return Path.home()


def default_data_dir() -> Path:
    docs = documents_dir()
    # 作者の環境では番号付きのフォルダを既に用意している
    numbered = docs / "82_作業時間記録"
    return numbered if numbered.is_dir() else docs / "作業時間記録"


def load_boot_config() -> dict:
    p = boot_config_path()
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_boot_config(cfg: dict) -> None:
    p = boot_config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def data_dir() -> Path:
    # 動作確認用：本番の記録を汚さないよう、環境変数で保存先を差し替えられる
    if os.environ.get("CASE_TIMER_DATA_DIR"):
        return Path(os.environ["CASE_TIMER_DATA_DIR"])
    d = load_boot_config().get("data_dir")
    return Path(d) if d else default_data_dir()
