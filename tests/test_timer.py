from datetime import datetime, timedelta

import pytest

from app.db import Store, parse
from app.timer import Timer, IDLE, RUNNING, PAUSED


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, **kw):
        self.t += timedelta(**kw)


@pytest.fixture
def env(tmp_path):
    store = Store(tmp_path / "t.db")
    pa = store.add_project("prjA")
    a1, a2 = store.add_task(pa, "設計"), store.add_task(pa, "レビュー")
    clock = Clock(datetime(2026, 10, 8, 9, 0, 0))
    return store, Timer(store, clock), clock, a1, a2


def spans(store):
    return [(r["task_id"], r["start_at"][11:16], r["end_at"][11:16]) for r in store.list_records()]


def test_start_requires_selection(env):
    store, timer, clock, a1, a2 = env
    assert timer.press_start(None) == "invalid"
    assert timer.status == IDLE


def test_start_stop_records_one_span(env):
    store, timer, clock, a1, a2 = env
    assert timer.press_start(a1) == "started"
    clock.advance(minutes=30)
    assert timer.snapshot()["elapsed"] == 1800
    assert timer.stop() == "stopped"
    assert spans(store) == [(a1, "09:00", "09:30")]
    assert timer.snapshot()["elapsed"] == 0 and timer.status == IDLE


def test_pause_excludes_time(env):
    store, timer, clock, a1, a2 = env
    timer.press_start(a1)
    clock.advance(minutes=60)
    assert timer.press_start(a1) == "paused"
    clock.advance(minutes=60)  # 昼休み
    assert timer.snapshot()["elapsed"] == 3600
    assert timer.press_start(a1) == "resumed"
    clock.advance(minutes=30)
    assert timer.snapshot()["elapsed"] == 5400
    timer.stop()
    assert spans(store) == [(a1, "09:00", "10:00"), (a1, "11:00", "11:30")]


def test_switch_without_stop(env):
    store, timer, clock, a1, a2 = env
    timer.press_start(a1)
    clock.advance(minutes=20)
    assert timer.press_start(a2) == "switched"
    assert timer.snapshot()["elapsed"] == 0  # 新しいタスクは0から
    clock.advance(minutes=10)
    timer.stop()
    assert spans(store) == [(a1, "09:00", "09:20"), (a2, "09:20", "09:30")]


def test_switch_while_paused(env):
    store, timer, clock, a1, a2 = env
    timer.press_start(a1)
    clock.advance(minutes=20)
    timer.press_start(a1)  # 一時停止
    clock.advance(minutes=20)
    assert timer.press_start(a2) == "switched"
    clock.advance(minutes=5)
    timer.stop()
    assert spans(store) == [(a1, "09:00", "09:20"), (a2, "09:40", "09:45")]


def test_preset_switch_semantics(env):
    store, timer, clock, a1, a2 = env
    assert timer.switch_to(a1) == "started"
    assert timer.switch_to(a1) == "unchanged"  # 同じタスクで計測中なら何もしない（一時停止にはならない）
    timer.press_start(a1)  # 一時停止
    assert timer.switch_to(a1) == "resumed"
    assert timer.switch_to(a2) == "switched"


def test_midnight_split_by_tick(env):
    store, timer, clock, a1, a2 = env
    clock.t = datetime(2026, 10, 8, 23, 30)
    timer.press_start(a1)
    clock.t = datetime(2026, 10, 9, 0, 20)
    assert timer.tick() is True
    assert timer.snapshot()["elapsed"] == 50 * 60  # 表示は続けて数える
    clock.t = datetime(2026, 10, 9, 0, 40)
    timer.stop()
    recs = store.list_records()
    assert [(r["start_at"], r["end_at"]) for r in recs] == [
        ("2026-10-08 23:30:00", "2026-10-09 00:00:00"),
        ("2026-10-09 00:00:00", "2026-10-09 00:40:00"),
    ]


def test_long_span_split_into_days_on_stop(env):
    # tick が呼ばれなかった（スリープ等）まま複数日をまたいでも、日付ごとに分かれる
    store, timer, clock, a1, a2 = env
    clock.t = datetime(2026, 10, 8, 22, 0)
    timer.press_start(a1)
    clock.t = datetime(2026, 10, 10, 1, 0)
    timer.stop()
    days = [r["start_at"][:10] for r in store.list_records()]
    assert days == ["2026-10-08", "2026-10-09", "2026-10-10"]


def test_exclude_idle(env):
    store, timer, clock, a1, a2 = env
    timer.press_start(a1)
    clock.t = datetime(2026, 10, 8, 13, 10)
    assert timer.exclude_idle(datetime(2026, 10, 8, 12, 0), datetime(2026, 10, 8, 13, 5))
    assert timer.snapshot()["elapsed"] == (3 * 60 + 5) * 60
    clock.t = datetime(2026, 10, 8, 14, 0)
    timer.stop()
    assert spans(store) == [(a1, "09:00", "12:00"), (a1, "13:05", "14:00")]


def test_exclude_idle_ignored_when_not_running(env):
    store, timer, clock, a1, a2 = env
    assert not timer.exclude_idle(datetime(2026, 10, 8, 8, 0), datetime(2026, 10, 8, 8, 30))


def test_state_survives_restart_and_recovery(env):
    store, timer, clock, a1, a2 = env
    timer.press_start(a1)
    clock.advance(minutes=45)
    timer.tick()  # 生存時刻 09:45
    clock.advance(hours=10)  # ここでPCが落ちた想定
    t2 = Timer(store, clock)
    assert t2.recovery == {"task_id": a1, "start": "2026-10-08 09:00:00", "last_alive": "2026-10-08 09:45:00"}
    t2.resolve_recovery(keep=True)
    assert spans(store) == [(a1, "09:00", "09:45")]
    assert t2.status == IDLE and Timer(store, clock).recovery is None


def test_recovery_discard(env):
    store, timer, clock, a1, a2 = env
    timer.press_start(a1)
    clock.advance(minutes=45)
    t2 = Timer(store, clock)
    t2.resolve_recovery(keep=False)
    assert spans(store) == [] and t2.status == IDLE


def test_paused_state_restored_without_recovery(env):
    store, timer, clock, a1, a2 = env
    timer.press_start(a1)
    clock.advance(minutes=10)
    timer.press_start(a1)
    t2 = Timer(store, clock)
    assert t2.status == PAUSED and t2.recovery is None and t2.snapshot()["elapsed"] == 600
