"""定期監視：日付またぎ・無操作（休憩）の検知。

無操作は Windows の GetLastInputInfo（最後にキーボード・マウスが操作された時刻）で判定する。
スリープ中はこのループ自体が止まるので、ループ間隔が大きく空いたら「その間は操作なし」とみなす。
"""
import ctypes
import threading
import time
from datetime import datetime, timedelta

from .timer import RUNNING


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def idle_seconds() -> float:
    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(info)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    now = ctypes.windll.kernel32.GetTickCount() & 0xFFFFFFFF
    return ((now - info.dwTime) & 0xFFFFFFFF) / 1000.0


class IdleDetector:
    """計測中に一定時間操作がなく、その後操作が戻ったら on_return(開始, 終了) を呼ぶ（純粋ロジック、テスト可能）。"""

    BACK_SECONDS = 5  # 直近この秒数以内に操作があれば「戻ってきた」とみなす
    GAP_SECONDS = 60  # ループ間隔がこれ以上空いたらスリープ等とみなす

    def __init__(self, threshold_seconds):
        self.threshold = threshold_seconds
        self.idle_start = None
        self.last_check = None

    def check(self, now: datetime, idle_sec: float, running: bool):
        prev, self.last_check = self.last_check, now
        if not running:
            self.idle_start = None
            return None
        if prev and (now - prev).total_seconds() >= self.GAP_SECONDS and (now - prev).total_seconds() >= self.threshold:
            self.idle_start = min(self.idle_start or prev, prev)
        if self.idle_start is None and idle_sec >= self.threshold:
            self.idle_start = now - timedelta(seconds=idle_sec)
        if self.idle_start is not None and idle_sec <= self.BACK_SECONDS:
            start, end = self.idle_start, now - timedelta(seconds=idle_sec)
            self.idle_start = None
            if (end - start).total_seconds() >= self.threshold:
                return start.replace(microsecond=0), end.replace(microsecond=0)
        return None


class Monitor:
    def __init__(self, timer, get_idle_minutes, on_change, on_idle_return, on_new_day, interval=2.0):
        self.timer = timer
        self.get_idle_minutes = get_idle_minutes
        self.on_change = on_change
        self.on_idle_return = on_idle_return
        self.on_new_day = on_new_day
        self.interval = interval
        self.detector = IdleDetector(get_idle_minutes() * 60)
        self._stop = threading.Event()
        self._day = datetime.now().date()

    def start(self):
        threading.Thread(target=self._loop, name="monitor", daemon=True).start()

    def stop(self):
        self._stop.set()

    def _loop(self):
        while not self._stop.is_set():
            try:
                self._step()
            except Exception:
                import traceback
                traceback.print_exc()
            self._stop.wait(self.interval)

    def _step(self):
        now = datetime.now()
        if self.timer.tick():
            self.on_change()
        if now.date() != self._day:
            self._day = now.date()
            self.on_new_day()
        self.detector.threshold = self.get_idle_minutes() * 60
        hit = self.detector.check(now, idle_seconds(), self.timer.status == RUNNING)
        if hit:
            self.on_idle_return(*hit)
