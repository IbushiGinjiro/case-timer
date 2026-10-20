"""確認用のダミーデータ（プロジェクトA/B、9/1〜10/20の平日、時刻なしの手入力1件）を作る。

使い方：python tests/e2e/seed_dummy.py <空のデータフォルダ>
本番のデータフォルダには絶対に使わないこと。
"""
import sys, random
from datetime import datetime, timedelta
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))
from app.db import Store
s = Store(sys.argv[1] + r"\case-timer.db")
pa = s.add_project("プロジェクトA"); pb = s.add_project("プロジェクトB")
ta = [s.add_task(pa, "設計"), s.add_task(pa, "レビュー")]; tb = [s.add_task(pb, "打合せ"), s.add_task(pb, "資料作成")]
random.seed(1)
day = datetime(2026, 9, 1)
while day <= datetime(2026, 10, 20):
    if day.weekday() < 5:
        t = datetime.combine(day.date(), datetime.min.time()) + timedelta(hours=9)
        for _ in range(3):
            d = timedelta(minutes=random.randint(30, 150), seconds=random.randint(0, 59))
            s.add_record(random.choice(ta + tb), t, t + d); t += d + timedelta(minutes=10)
    day += timedelta(days=1)
s.add_record(ta[0], datetime(2026, 10, 17), datetime(2026, 10, 17, 1, 30), no_time=True)
print("seeded", len(s.list_records()))
