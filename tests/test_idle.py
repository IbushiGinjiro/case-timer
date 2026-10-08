from datetime import datetime, timedelta

from app.hotkeys import parse, MOD
from app.monitor import IdleDetector

T0 = datetime(2026, 10, 8, 12, 0, 0)


def run(det, steps):
    """steps: [(経過秒, 無操作秒, 計測中)] を順に流し、検知結果を返す"""
    hits = []
    for sec, idle, running in steps:
        h = det.check(T0 + timedelta(seconds=sec), idle, running)
        if h:
            hits.append(h)
    return hits


def test_lunch_break_detected_on_return():
    det = IdleDetector(15 * 60)
    steps = [(s, s, True) for s in range(0, 3600 + 1, 60)]  # 1時間操作なし
    steps.append((3602, 1, True))  # 戻ってきた
    hits = run(det, steps)
    assert hits == [(T0, T0 + timedelta(seconds=3601))]


def test_short_idle_ignored():
    det = IdleDetector(15 * 60)
    assert run(det, [(0, 0, True), (600, 600, True), (602, 1, True)]) == []


def test_not_running_resets():
    det = IdleDetector(15 * 60)
    hits = run(det, [(0, 0, True), (1200, 1200, True), (1210, 1210, False), (1212, 1, True)])
    assert hits == []


def test_sleep_gap_counts_as_idle():
    # スリープでループが止まり、復帰直後の無操作秒数が小さく見える場合
    det = IdleDetector(15 * 60)
    hits = run(det, [(0, 0, True), (2, 2, True), (2 * 3600, 3, True)])
    assert hits == [(T0 + timedelta(seconds=2), T0 + timedelta(seconds=2 * 3600 - 3))]


def test_hotkey_parse():
    assert parse("ctrl+alt+1") == (MOD["ctrl"] | MOD["alt"], ord("1"))
    assert parse("Ctrl+Alt+Shift+2") == (MOD["ctrl"] | MOD["alt"] | MOD["shift"], ord("2"))
    assert parse("ctrl+f5") == (MOD["ctrl"], 0x74)
    for bad in ["1", "ctrl+", "hyper+1", "ctrl+enter"]:
        try:
            parse(bad)
            assert False, bad
        except ValueError:
            pass
