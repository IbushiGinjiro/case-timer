"""case-timer 本体：ウィンドウ・画面向けAPI・ショートカット・監視をつなぐ。"""
import ctypes
import json
import shutil
import sys
import threading
from datetime import date, datetime
from pathlib import Path

import webview

from . import __version__, autostart, paths
from .db import Store, parse
from .hotkeys import HotkeyManager
from .monitor import Monitor
from .timer import Timer, IDLE

MAIN_SIZE = (556, 428)  # 画面の内側の大きさ（resize()で指定した値がそのまま内側になる）
MINI_SIZE = (380, 52)
MINI_ALPHA = 0.55
BG = "#23243a"
# メイン画面の背景を抜くための色。WebView2 の背景を透明にし、その下のフォームをこの色で塗って
# 「この色は透明」と指定する。抜けた部分はクリックも後ろのウィンドウに通る
KEY_COLOR = (0x01, 0x02, 0x03)


def set_window_alpha(title: str, alpha: float):
    """背景の透明化（KEY_COLOR）と、ウィンドウ全体の不透明度（ミニモード用）。WebView2でも効くことを確認済み。"""
    user32 = ctypes.windll.user32
    hwnd = user32.FindWindowW(None, title)
    if not hwnd:
        return
    GWL_EXSTYLE, WS_EX_LAYERED, LWA_COLORKEY, LWA_ALPHA = -20, 0x80000, 0x1, 0x2
    user32.GetWindowLongW.restype = ctypes.c_long
    ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex | WS_EX_LAYERED)
    r, g, b = KEY_COLOR
    user32.SetLayeredWindowAttributes(hwnd, r | g << 8 | b << 16, int(alpha * 255), LWA_COLORKEY | LWA_ALPHA)


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", RECT), ("rcWork", RECT), ("dwFlags", ctypes.c_ulong)]


def resize_keep_bottom_left(title: str, w: int, h: int) -> bool:
    """左下の位置を変えずにウィンドウの大きさを変える（ミニモードの切替で位置がずれないように）。

    w, h は画面の内側の大きさ（CSSピクセル）。枠なしウィンドウなので外側＝内側で、DPI倍率を掛けた値になる。
    画面からはみ出す場合は作業領域（タスクバーを除いた範囲）に収める。
    """
    user32 = ctypes.windll.user32
    hwnd = user32.FindWindowW(None, title)
    if not hwnd:
        return False
    scale = (user32.GetDpiForWindow(hwnd) or 96) / 96
    pw, ph = round(w * scale), round(h * scale)
    r = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    x, y = r.left, r.bottom - ph
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(mi)
    if user32.GetMonitorInfoW(user32.MonitorFromWindow(hwnd, 2), ctypes.byref(mi)):
        work = mi.rcWork
        x = max(work.left, min(x, work.right - pw))
        y = max(work.top, min(y, work.bottom - ph))
    SWP_NOZORDER, SWP_NOACTIVATE = 0x0004, 0x0010
    return bool(user32.SetWindowPos(hwnd, None, x, y, pw, ph, SWP_NOZORDER | SWP_NOACTIVATE))


class App:
    MAIN_TITLE = "case-timer"
    ANALYSIS_TITLE = "case-timer 分析"

    def __init__(self):
        self.data_dir = paths.data_dir()
        self.store = Store(self.data_dir / paths.DB_FILENAME)
        self.timer = Timer(self.store)
        self.selection = {"project_id": None, "task_id": None}
        self.main = None
        self.analysis = None
        self.mini = False
        self.pending_idle = None
        self.hotkeys = HotkeyManager(self.on_hotkey)
        self.monitor = None

    # ---------- 画面への通知 ----------
    def push(self, event: str, payload=None):
        if self.main:
            try:
                self.main.evaluate_js(f"window.ct && ct.onEvent({json.dumps(event)}, {json.dumps(payload, ensure_ascii=False)})")
            except Exception:
                pass

    def push_state(self):
        self.push("state", self.state())

    def state(self):
        return {"timer": self.timer.snapshot(), "selection": self.selection, "presets": self.presets()}

    # ---------- 選択・プリセット ----------
    def valid_selection(self, project_id, task_id):
        for p in self.store.list_projects():
            if p["id"] == project_id and not p["done"]:
                if any(t["id"] == task_id and not t["done"] for t in p["tasks"]):
                    return {"project_id": project_id, "task_id": task_id}
                return {"project_id": project_id, "task_id": None}
        return {"project_id": None, "task_id": None}

    def initial_selection(self):
        snap = self.timer.snapshot()
        if snap["status"] != IDLE and snap["task_id"]:
            return {"project_id": snap["project_id"], "task_id": snap["task_id"]}
        s = self.store.get_settings()
        today = date.today().isoformat()
        first_today = self.store.get("last_launch_date") != today
        self.store.set("last_launch_date", today)
        if s["startup_mode"] == "fixed" and first_today and s.get("fixed_task_id"):
            return self.valid_selection(s.get("fixed_project_id"), s.get("fixed_task_id"))
        last = self.store.get("last_selection") or {}
        return self.valid_selection(last.get("project_id"), last.get("task_id"))

    def set_selection(self, project_id, task_id):
        self.selection = {"project_id": project_id, "task_id": task_id}
        self.store.set("last_selection", self.selection)

    def presets(self):
        raw = self.store.get("presets") or [None, None, None]
        out = []
        for p in (raw + [None, None, None])[:3]:
            t = self.store.task(p["task_id"]) if p and p.get("task_id") else None
            out.append({"project_id": t["project_id"], "task_id": t["id"], "label": t["name"], "full": f'{t["project_name"]} / {t["name"]}'} if t else None)
        return out

    def save_preset(self, i, project_id, task_id):
        raw = (self.store.get("presets") or [None, None, None]) + [None, None, None]
        raw = raw[:3]
        raw[i] = {"project_id": project_id, "task_id": task_id} if task_id else None
        self.store.set("presets", raw)

    def use_preset(self, i):
        p = self.presets()[i]
        if not p:
            return "empty"
        self.set_selection(p["project_id"], p["task_id"])
        return self.timer.switch_to(p["task_id"])

    # ---------- ショートカット ----------
    def hotkey_bindings(self):
        hk = self.store.get_settings()["hotkeys"]
        b = {"edit": hk["edit"]}
        for i in (1, 2, 3):
            b[f"preset{i}"] = hk[f"preset{i}"]
            b[f"save{i}"] = "shift+" + hk[f"preset{i}"]  # 登録は同じキー＋Shift
        return b

    def start_hotkeys(self):
        return self.hotkeys.start(self.hotkey_bindings())

    def on_hotkey(self, name):
        if name == "edit":
            self.push("toggleEdit")
            return
        i = int(name[-1]) - 1
        if name.startswith("preset"):
            result = self.use_preset(i)
            self.push_state()
            self.push("flash", {"result": result, "preset": i})
        elif name.startswith("save"):
            sel = self.selection
            if sel.get("task_id"):
                self.save_preset(i, sel["project_id"], sel["task_id"])
                self.push_state()
                self.push("presetSaved", {"preset": i})
            else:
                self.push("flash", {"result": "invalid", "preset": i})

    # ---------- 監視 ----------
    def on_idle_return(self, start: datetime, end: datetime):
        self.pending_idle = (start, end)
        self.push("idleReturn", {"start": start.strftime("%H:%M"), "end": end.strftime("%H:%M"),
                                 "minutes": int((end - start).total_seconds() // 60), "label": self.timer.snapshot()["label"]})

    def on_new_day(self):
        s = self.store.get_settings()
        if self.timer.status == IDLE and s["startup_mode"] == "fixed" and s.get("fixed_task_id"):
            self.store.set("last_launch_date", date.today().isoformat())
            sel = self.valid_selection(s.get("fixed_project_id"), s.get("fixed_task_id"))
            self.set_selection(sel["project_id"], sel["task_id"])
            self.push_state()

    # ---------- 保存先 ----------
    def switch_data_dir(self, new_dir: Path):
        new_dir = Path(new_dir)
        if new_dir.resolve() == self.data_dir.resolve():
            return "same"
        if self.timer.status != IDLE:
            return "running"
        new_db = new_dir / paths.DB_FILENAME
        new_dir.mkdir(parents=True, exist_ok=True)
        existed = new_db.exists()
        self.store.close()
        if not existed:
            shutil.copy2(self.data_dir / paths.DB_FILENAME, new_db)
        cfg = paths.load_boot_config()
        cfg["data_dir"] = str(new_dir)
        paths.save_boot_config(cfg)
        self.data_dir = new_dir
        self.store = Store(new_db)
        self.timer = Timer(self.store)
        self.monitor.timer = self.timer
        return "opened" if existed else "copied"

    # ---------- ウィンドウ ----------
    def open_analysis(self):
        if self.analysis:
            try:
                self.analysis.restore()
                self.analysis.show()
                self.analysis.evaluate_js("window.reloadData && reloadData()")
                return
            except Exception:
                self.analysis = None
        self.analysis = webview.create_window(
            self.ANALYSIS_TITLE, url=str(paths.WEB_DIR / "analysis.html"), js_api=self.api,
            width=1180, height=880, min_size=(720, 500), background_color=BG)
        self.analysis.events.closed += lambda: setattr(self, "analysis", None)

    def set_mini(self, on: bool):
        self.mini = on
        w, h = MINI_SIZE if on else MAIN_SIZE
        if not resize_keep_bottom_left(self.MAIN_TITLE, w, h):
            self.main.resize(w, h)
        set_window_alpha(self.MAIN_TITLE, MINI_ALPHA if on else 1.0)

    def on_main_loaded(self):
        self.main.resize(*(MINI_SIZE if self.mini else MAIN_SIZE))
        try:
            import System
            from System.Drawing import Color
            form = self.main.native

            def apply_key():
                form.BackColor = form.TransparencyKey = Color.FromArgb(255, *KEY_COLOR)
            form.Invoke(System.Action(apply_key))
        except Exception as e:  # 透明にできなくても動作には影響しない
            print("背景の透明化に失敗:", e)
        set_window_alpha(self.MAIN_TITLE, MINI_ALPHA if self.mini else 1.0)

    def set_shape(self, rects):
        """クリックを受け取る範囲（画面の内側の座標、物理ピクセル）。その下のフォームだけを KEY_COLOR 以外で塗る。"""
        try:
            import System
            from System.Drawing import Bitmap, Color, Graphics, Rectangle, SolidBrush
            form = self.main.native

            def paint():
                size = form.ClientSize
                bmp = Bitmap(max(1, size.Width), max(1, size.Height))
                g = Graphics.FromImage(bmp)
                g.Clear(Color.FromArgb(255, *KEY_COLOR))
                brush = SolidBrush(Color.FromArgb(255, 34, 34, 34))
                for x, y, w, h in rects:
                    g.FillRectangle(brush, Rectangle(int(x), int(y), int(w), int(h)))
                brush.Dispose(); g.Dispose()
                old, form.BackgroundImage = form.BackgroundImage, bmp
                if old is not None:
                    old.Dispose()
            form.Invoke(System.Action(paint))
        except Exception as e:
            print("クリック範囲の設定に失敗:", e)

    def run(self):
        self.api = Api(self)
        self.selection = self.initial_selection()
        pos = self.store.get("window_pos") or {}
        self.main = webview.create_window(
            self.MAIN_TITLE, url=str(paths.WEB_DIR / "main.html"), js_api=self.api,
            width=MAIN_SIZE[0], height=MAIN_SIZE[1], x=pos.get("x"), y=pos.get("y"),
            frameless=True, easy_drag=False, on_top=True, resizable=False,
            min_size=(200, 40), transparent=True)
        # 次回起動時は通常モードで開くので、位置は通常モードのときだけ覚える
        self.main.events.moved += lambda x, y: None if self.mini else self.store.set("window_pos", {"x": x, "y": y})
        self.main.events.closed += self.on_main_closed
        # create_window の width/height は枠ぶん小さくなるので、表示後に resize() で内側の大きさをそろえる
        self.main.events.loaded += self.on_main_loaded
        self.monitor = Monitor(self.timer, lambda: self.store.get_settings()["idle_minutes"],
                               self.push_state, self.on_idle_return, self.on_new_day)
        self.hotkey_errors = self.start_hotkeys()
        self.monitor.start()
        webview.start(debug="--debug" in sys.argv)
        self.hotkeys.stop()
        self.monitor.stop()

    def on_main_closed(self):
        if self.analysis:
            try:
                self.analysis.destroy()
            except Exception:
                pass


class Api:
    """画面（JS）から window.pywebview.api.xxx() で呼ばれる。属性は _ 始まりにしてJSへ公開しない。"""

    def __init__(self, app: App):
        self._app = app

    # ---------- メイン画面 ----------
    def bootstrap(self):
        a = self._app
        return {**a.state(), "projects": a.store.list_projects(), "settings": a.store.get_settings(),
                "recovery": self._recovery(), "hotkey_errors": a.hotkey_errors, "data_dir": str(a.data_dir),
                "autostart": autostart.is_enabled(), "version": __version__}

    def _recovery(self):
        r = self._app.timer.recovery
        if not r:
            return None
        t = self._app.store.task(r["task_id"])
        return {**r, "label": f'{t["project_name"]} / {t["name"]}' if t else "?"}

    def get_state(self):
        return self._app.state()

    def set_selection(self, project_id, task_id):
        self._app.set_selection(project_id, task_id)

    def press_start(self, project_id, task_id):
        a = self._app
        a.set_selection(project_id, task_id)
        result = a.timer.press_start(task_id)
        return {"result": result, **a.state()}

    def press_stop(self):
        result = self._app.timer.stop()
        return {"result": result, **self._app.state()}

    def use_preset(self, i):
        result = self._app.use_preset(int(i))
        return {"result": result, **self._app.state()}

    def save_preset(self, i, project_id, task_id):
        self._app.save_preset(int(i), project_id, task_id)
        return self._app.state()

    def resolve_idle(self, exclude):
        a = self._app
        if exclude and a.pending_idle:
            a.timer.exclude_idle(*a.pending_idle)
        a.pending_idle = None
        return a.state()

    def resolve_recovery(self, keep):
        self._app.timer.resolve_recovery(bool(keep))
        return self._app.state()

    # ---------- 編集モード ----------
    def _projects(self):
        return {"projects": self._app.store.list_projects(), **self._app.state()}

    def add_project(self, name):
        pid = self._app.store.add_project(name)
        return {**self._projects(), "new_id": pid}

    def rename_project(self, project_id, name):
        self._app.store.rename_project(project_id, name)
        return self._projects()

    def set_project_done(self, project_id, done):
        self._app.store.set_project_done(project_id, bool(done))
        return self._projects()

    def add_task(self, project_id, name):
        tid = self._app.store.add_task(project_id, name)
        return {**self._projects(), "new_id": tid}

    def rename_task(self, task_id, name):
        self._app.store.rename_task(task_id, name)
        return self._projects()

    def set_task_done(self, task_id, done):
        self._app.store.set_task_done(task_id, bool(done))
        return self._projects()

    def save_settings(self, settings):
        a = self._app
        before = a.store.get_settings()["hotkeys"]
        s = a.store.save_settings(settings)
        if s["hotkeys"] != before:
            a.hotkey_errors = a.start_hotkeys()
        return {"settings": s, "hotkey_errors": a.hotkey_errors}

    def set_autostart(self, on):
        autostart.set_enabled(bool(on))
        return autostart.is_enabled()

    def choose_data_dir(self):
        a = self._app
        picked = a.main.create_file_dialog(webview.FOLDER_DIALOG, directory=str(a.data_dir))
        if not picked:
            return {"result": "cancel", "data_dir": str(a.data_dir)}
        result = a.switch_data_dir(Path(picked[0] if isinstance(picked, (list, tuple)) else picked))
        return {"result": result, "data_dir": str(a.data_dir), **self.bootstrap()}

    # ---------- ウィンドウ ----------
    def set_mini(self, on):
        self._app.set_mini(bool(on))

    def set_shape(self, rects):
        self._app.set_shape(rects)

    def set_hover(self, hovering):
        if self._app.mini:
            set_window_alpha(App.MAIN_TITLE, 1.0 if hovering else MINI_ALPHA)

    def open_analysis(self):
        self._app.open_analysis()

    def quit(self, stop_timer):
        if stop_timer:
            self._app.timer.stop()
        threading.Timer(0.1, self._app.main.destroy).start()

    # ---------- 分析画面 ----------
    def analysis_data(self):
        s = self._app.store
        return {"projects": s.list_projects(), "records": s.list_records(), "today": date.today().isoformat()}

    def add_record(self, task_id, start, end):
        self._app.store.add_record(int(task_id), parse(start), parse(end))
        return self.analysis_data()

    def update_record(self, record_id, task_id, start, end):
        self._app.store.update_record(int(record_id), int(task_id), parse(start), parse(end))
        return self.analysis_data()

    def delete_record(self, record_id):
        self._app.store.delete_record(int(record_id))
        return self.analysis_data()

    def save_csv(self, filename, text):
        win = self._app.analysis or self._app.main
        picked = win.create_file_dialog(webview.SAVE_DIALOG, directory=str(self._app.data_dir),
                                        save_filename=filename, file_types=("CSV (*.csv)",))
        if not picked:
            return None
        path = picked[0] if isinstance(picked, (list, tuple)) else picked
        Path(path).write_text(text, encoding="utf-8-sig")
        return str(path)


def main():
    App().run()
