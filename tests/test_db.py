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
