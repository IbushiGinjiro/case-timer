"""SQLite への保存。

記録（records）は「連続して作業していた区間」1つにつき1行。一時停止・切替・日付またぎ・
休憩の除外はすべて区間を区切ることで表現する（分析では区間の長さを足すだけでよい）。
"""
import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

TS = "%Y-%m-%d %H:%M:%S"

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  done INTEGER NOT NULL DEFAULT 0,
  sort INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES projects(id),
  name TEXT NOT NULL,
  done INTEGER NOT NULL DEFAULT 0,
  sort INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS records (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id INTEGER NOT NULL REFERENCES tasks(id),
  start_at TEXT NOT NULL,
  end_at TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_records_start ON records(start_at);
CREATE TABLE IF NOT EXISTS kv (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""

DEFAULT_SETTINGS = {
    "startup_mode": "last",        # last: 直前のタスクを引き継ぐ / fixed: 決まったタスクで始める
    "fixed_project_id": None,
    "fixed_task_id": None,
    "idle_minutes": 15,
    "hotkeys": {
        "preset1": "ctrl+alt+1",
        "preset2": "ctrl+alt+2",
        "preset3": "ctrl+alt+3",
        "edit": "ctrl+alt+0",
    },
}


def fmt(dt: datetime) -> str:
    return dt.strftime(TS)


def parse(s: str) -> datetime:
    return datetime.strptime(s, TS)


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # pywebview のAPI呼び出し・ショートカット・監視スレッドから触るので、1接続をロックで守る
        self._lock = threading.RLock()
        # OneDrive上に置くので、WAL（-wal/-shmの別ファイル）は使わず既定のジャーナルにする
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    def close(self):
        with self._lock:
            self._conn.close()

    def _exec(self, sql, params=()):
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    def _all(self, sql, params=()):
        with self._lock:
            return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    # ---------- kv / 設定 ----------
    def get(self, key, default=None):
        rows = self._all("SELECT value FROM kv WHERE key = ?", (key,))
        return json.loads(rows[0]["value"]) if rows else default

    def set(self, key, value):
        self._exec("INSERT INTO kv(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                   (key, json.dumps(value, ensure_ascii=False)))

    def get_settings(self) -> dict:
        saved = self.get("settings", {}) or {}
        merged = {**DEFAULT_SETTINGS, **saved}
        merged["hotkeys"] = {**DEFAULT_SETTINGS["hotkeys"], **(saved.get("hotkeys") or {})}
        return merged

    def save_settings(self, settings: dict) -> dict:
        current = self.get_settings()
        merged = {**current, **settings}
        merged["hotkeys"] = {**current["hotkeys"], **(settings.get("hotkeys") or {})}
        self.set("settings", merged)
        return self.get_settings()

    # ---------- プロジェクト・タスク ----------
    def list_projects(self) -> list:
        projects = self._all("SELECT id, name, done FROM projects ORDER BY sort, id")
        tasks = self._all("SELECT id, project_id, name, done FROM tasks ORDER BY sort, id")
        for p in projects:
            p["done"] = bool(p["done"])
            p["tasks"] = [{"id": t["id"], "name": t["name"], "done": bool(t["done"])}
                          for t in tasks if t["project_id"] == p["id"]]
        return projects

    def add_project(self, name: str) -> int:
        name = name.strip()
        if not name:
            raise ValueError("プロジェクト名が空です")
        sort = self._all("SELECT COALESCE(MAX(sort), 0) + 1 AS s FROM projects")[0]["s"]
        return self._exec("INSERT INTO projects(name, sort, created_at) VALUES(?, ?, ?)",
                          (name, sort, fmt(datetime.now()))).lastrowid

    def rename_project(self, project_id: int, name: str):
        name = name.strip()
        if not name:
            raise ValueError("プロジェクト名が空です")
        self._exec("UPDATE projects SET name = ? WHERE id = ?", (name, project_id))

    def set_project_done(self, project_id: int, done: bool):
        self._exec("UPDATE projects SET done = ? WHERE id = ?", (int(done), project_id))

    def add_task(self, project_id: int, name: str) -> int:
        name = name.strip()
        if not name:
            raise ValueError("タスク名が空です")
        sort = self._all("SELECT COALESCE(MAX(sort), 0) + 1 AS s FROM tasks WHERE project_id = ?", (project_id,))[0]["s"]
        return self._exec("INSERT INTO tasks(project_id, name, sort, created_at) VALUES(?, ?, ?, ?)",
                          (project_id, name, sort, fmt(datetime.now()))).lastrowid

    def rename_task(self, task_id: int, name: str):
        name = name.strip()
        if not name:
            raise ValueError("タスク名が空です")
        self._exec("UPDATE tasks SET name = ? WHERE id = ?", (name, task_id))

    def set_task_done(self, task_id: int, done: bool):
        self._exec("UPDATE tasks SET done = ? WHERE id = ?", (int(done), task_id))

    def task(self, task_id):
        rows = self._all("""SELECT t.id, t.name, t.project_id, p.name AS project_name
                            FROM tasks t JOIN projects p ON p.id = t.project_id WHERE t.id = ?""", (task_id,))
        return rows[0] if rows else None

    # ---------- 記録 ----------
    def add_record(self, task_id: int, start: datetime, end: datetime) -> int:
        if end <= start:
            raise ValueError("終了が開始より前です")
        return self._exec("INSERT INTO records(task_id, start_at, end_at) VALUES(?, ?, ?)",
                          (task_id, fmt(start), fmt(end))).lastrowid

    def update_record(self, record_id: int, task_id: int, start: datetime, end: datetime):
        if end <= start:
            raise ValueError("終了が開始より前です")
        self._exec("UPDATE records SET task_id = ?, start_at = ?, end_at = ? WHERE id = ?",
                   (task_id, fmt(start), fmt(end), record_id))

    def delete_record(self, record_id: int):
        self._exec("DELETE FROM records WHERE id = ?", (record_id,))

    def list_records(self) -> list:
        return self._all("SELECT id, task_id, start_at, end_at FROM records ORDER BY start_at")
