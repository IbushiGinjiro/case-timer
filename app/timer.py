"""計測の状態管理（START/STOP・一時停止・切替・日付またぎ・休憩の除外・前回終了時の取り残し）。

状態は Store の kv に毎回書き出すので、アプリやPCが落ちても次回起動時に復元・確認できる。
画面に出す時間は「STARTしてからSTOP（または切替）までの、一時停止を除いた合計」。
"""
import threading
from datetime import datetime, timedelta

from .db import Store, fmt, parse

IDLE, RUNNING, PAUSED = "idle", "running", "paused"
ALIVE_INTERVAL = timedelta(seconds=30)


def _trunc(dt: datetime) -> datetime:
    return dt.replace(microsecond=0)


class Timer:
    def __init__(self, store: Store, clock=datetime.now):
        self.store = store
        self.clock = clock
        self._lock = threading.RLock()
        self._last_alive_write = None
        s = store.get("timer") or {}
        self.status = s.get("status", IDLE)
        self.task_id = s.get("task_id")
        self.seg_start = parse(s["seg_start"]) if s.get("seg_start") else None
        self.acc = float(s.get("acc", 0))
        # 前回、計測中のままアプリが終わっていた場合は、起動時にユーザーへ確認する
        self.recovery = None
        if self.status == RUNNING and self.seg_start:
            alive = store.get("alive")
            last = parse(alive) if alive else self.seg_start
            self.recovery = {"task_id": self.task_id, "start": fmt(self.seg_start), "last_alive": fmt(max(last, self.seg_start))}

    # ---------- 内部 ----------
    def _save(self):
        self.store.set("timer", {
            "status": self.status, "task_id": self.task_id,
            "seg_start": fmt(self.seg_start) if self.seg_start else None, "acc": self.acc,
        })

    def _write_records(self, start: datetime, end: datetime):
        """区間を記録する。0時をまたぐ場合は日付ごとに分ける。"""
        start, end = _trunc(start), _trunc(end)
        while start < end:
            midnight = datetime.combine(start.date() + timedelta(days=1), datetime.min.time())
            piece_end = min(end, midnight)
            if piece_end > start:
                self.store.add_record(self.task_id, start, piece_end)
            start = piece_end

    def _close_segment(self, end: datetime):
        if self.seg_start is None:
            return
        if end > self.seg_start:
            self._write_records(self.seg_start, end)
            self.acc += (end - self.seg_start).total_seconds()
        self.seg_start = None

    def _begin(self, task_id: int, now: datetime):
        self.status, self.task_id, self.seg_start, self.acc = RUNNING, task_id, now, 0.0
        self._save()

    def _reset(self):
        self.status, self.task_id, self.seg_start, self.acc = IDLE, None, None, 0.0
        self._save()

    # ---------- 操作 ----------
    def press_start(self, task_id):
        """START：未選択なら何もしない／停止中なら開始／同じタスクなら一時停止・再開／違うタスクなら切替。"""
        with self._lock:
            if not task_id:
                return "invalid"
            now = self.clock()
            if self.status == IDLE:
                self._begin(task_id, now)
                return "started"
            if task_id == self.task_id:
                if self.status == RUNNING:
                    self._close_segment(now)
                    self.status = PAUSED
                    self._save()
                    return "paused"
                self.seg_start = now
                self.status = RUNNING
                self._save()
                return "resumed"
            self._close_segment(now)
            self._begin(task_id, now)
            return "switched"

    def switch_to(self, task_id):
        """プリセット：そのタスクで計測中にする（同じタスクで一時停止中なら再開、計測中なら何もしない）。"""
        with self._lock:
            if self.status != IDLE and task_id == self.task_id:
                return self.press_start(task_id) if self.status == PAUSED else "unchanged"
            return self.press_start(task_id)

    def stop(self):
        with self._lock:
            if self.status == IDLE:
                return "invalid"
            self._close_segment(self.clock())
            self._reset()
            return "stopped"

    def tick(self):
        """定期的に呼ぶ。日付またぎの区切りと、生存時刻の記録を行う。区切った場合は True。"""
        with self._lock:
            now = self.clock()
            changed = False
            if self.status == RUNNING and self.seg_start and self.seg_start.date() < now.date():
                midnight = datetime.combine(now.date(), datetime.min.time())
                self._close_segment(midnight)
                self.seg_start = midnight
                self._save()
                changed = True
            if self.status == RUNNING and (self._last_alive_write is None or now - self._last_alive_write >= ALIVE_INTERVAL):
                self.store.set("alive", fmt(now))
                self._last_alive_write = now
            return changed

    def exclude_idle(self, idle_start: datetime, idle_end: datetime):
        """無操作だった区間を作業時間から除く。計測中のときだけ有効。"""
        with self._lock:
            if self.status != RUNNING or self.seg_start is None or idle_end <= idle_start:
                return False
            if self.seg_start < idle_start:
                self._close_segment(idle_start)
            self.seg_start = max(idle_end, self.seg_start or idle_end)
            self._save()
            return True

    def resolve_recovery(self, keep: bool):
        """前回の取り残し。keep=True なら最後に動いていた時刻までを記録、False なら記録しない。"""
        with self._lock:
            r = self.recovery
            self.recovery = None
            if not r:
                return
            if keep:
                self.task_id = r["task_id"]
                self.seg_start = parse(r["start"])
                self._close_segment(parse(r["last_alive"]))
            self._reset()

    # ---------- 表示用 ----------
    def snapshot(self) -> dict:
        with self._lock:
            elapsed = self.acc
            if self.status == RUNNING and self.seg_start:
                elapsed += max(0.0, (self.clock() - self.seg_start).total_seconds())
            t = self.store.task(self.task_id) if self.task_id else None
            return {
                "status": self.status, "task_id": self.task_id,
                "project_id": t["project_id"] if t else None,
                "label": f'{t["project_name"]} / {t["name"]}' if t else "",
                "elapsed": elapsed,
            }
