from datetime import datetime

import pytest

from app.db import Store


def test_projects_tasks_done_and_rename(tmp_path):
    s = Store(tmp_path / "t.db")
    p = s.add_project("prjA")
    t = s.add_task(p, "設計")
    s.rename_project(p, "prjA 改")
    s.rename_task(t, "基本設計")
    s.set_project_done(p, True)
    [proj] = s.list_projects()
    assert proj["name"] == "prjA 改" and proj["done"] is True
    assert proj["tasks"] == [{"id": t, "name": "基本設計", "done": False}]
    with pytest.raises(ValueError):
        s.add_project("  ")


def test_record_validation(tmp_path):
    s = Store(tmp_path / "t.db")
    t = s.add_task(s.add_project("p"), "t")
    with pytest.raises(ValueError):
        s.add_record(t, datetime(2026, 1, 1, 10), datetime(2026, 1, 1, 9))
    rid = s.add_record(t, datetime(2026, 1, 1, 9), datetime(2026, 1, 1, 10))
    s.update_record(rid, t, datetime(2026, 1, 1, 9), datetime(2026, 1, 1, 11))
    assert s.list_records()[0]["end_at"] == "2026-01-01 11:00:00"
    s.delete_record(rid)
    assert s.list_records() == []


def test_settings_merge_defaults(tmp_path):
    s = Store(tmp_path / "t.db")
    s.save_settings({"idle_minutes": 20, "hotkeys": {"preset1": "ctrl+alt+7"}})
    st = s.get_settings()
    assert st["idle_minutes"] == 20
    assert st["hotkeys"]["preset1"] == "ctrl+alt+7" and st["hotkeys"]["edit"] == "ctrl+alt+0"


def test_no_time_record_and_migration(tmp_path):
    import sqlite3
    from datetime import datetime
    path = tmp_path / "old.db"
    # v1.1の形（no_time列なし）のDBを作ってから開くと、列が足されて既存の記録は時刻ありのまま読める
    con = sqlite3.connect(path)
    con.executescript("""CREATE TABLE projects (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0, sort INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
CREATE TABLE tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, name TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0, sort INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
CREATE TABLE records (id INTEGER PRIMARY KEY AUTOINCREMENT, task_id INTEGER NOT NULL, start_at TEXT NOT NULL, end_at TEXT NOT NULL, note TEXT NOT NULL DEFAULT '');
INSERT INTO projects(name, created_at) VALUES('p', '2026-10-01 00:00:00');
INSERT INTO tasks(project_id, name, created_at) VALUES(1, 't', '2026-10-01 00:00:00');
INSERT INTO records(task_id, start_at, end_at) VALUES(1, '2026-10-01 09:00:00', '2026-10-01 10:00:00');""")
    con.commit(); con.close()
    store = Store(path)
    assert store.list_records()[0]["no_time"] == 0
    store.add_record(1, datetime(2026, 10, 2), datetime(2026, 10, 2, 1, 30), no_time=True)
    assert store.list_records()[1]["no_time"] == 1
    # 休憩の除外は時刻なしの記録を削らない
    assert store.cut_records(1, datetime(2026, 10, 1, 23, 0), datetime(2026, 10, 2, 8, 0)) == 0
    assert len(store.list_records()) == 2
