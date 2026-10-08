"""グローバルショートカット（Win32 RegisterHotKey）。

キーボードフックではなくOSのホットキー登録を使うので、他のアプリへの入力を覗かない。
Shift付きの数字（!など）も仮想キーコードで判定できる。
"""
import ctypes
import threading
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

MOD = {"alt": 0x0001, "ctrl": 0x0002, "shift": 0x0004, "win": 0x0008}
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012


def parse(combo: str):
    """'ctrl+alt+1' → (修飾キー, 仮想キーコード)。解釈できなければ ValueError。"""
    parts = [p.strip().lower() for p in combo.split("+") if p.strip()]
    if not parts:
        raise ValueError("空のショートカット")
    mods, key = 0, parts[-1]
    for p in parts[:-1]:
        if p not in MOD:
            raise ValueError(f"修飾キーが不明: {p}")
        mods |= MOD[p]
    if len(key) == 1 and key.isalnum():
        vk = ord(key.upper())
    elif key.startswith("f") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        vk = 0x70 + int(key[1:]) - 1
    else:
        raise ValueError(f"キーが不明: {key}")
    if mods == 0:
        raise ValueError("Ctrl/Alt/Shift/Win のどれかが必要です")
    return mods, vk


class HotkeyManager:
    """bindings: {名前: 'ctrl+alt+1'} を登録し、押されたら callback(名前) を別スレッドで呼ぶ。"""

    def __init__(self, callback):
        self.callback = callback
        self._thread = None
        self._thread_id = None
        self.errors = {}

    def start(self, bindings: dict):
        self.stop()
        ready = threading.Event()
        self.errors = {}

        def loop():
            self._thread_id = kernel32.GetCurrentThreadId()
            ids = {}
            for i, (name, combo) in enumerate(bindings.items(), start=1):
                try:
                    mods, vk = parse(combo)
                except ValueError as e:
                    self.errors[name] = str(e)
                    continue
                if user32.RegisterHotKey(None, i, mods | MOD_NOREPEAT, vk):
                    ids[i] = name
                else:
                    self.errors[name] = "他のアプリが使用中です"
            ready.set()
            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY and msg.wParam in ids:
                    try:
                        self.callback(ids[msg.wParam])
                    except Exception:  # ショートカットの処理失敗でループを止めない
                        import traceback
                        traceback.print_exc()
            for i in ids:
                user32.UnregisterHotKey(None, i)

        self._thread = threading.Thread(target=loop, name="hotkeys", daemon=True)
        self._thread.start()
        ready.wait(3)
        return self.errors

    def stop(self):
        if self._thread and self._thread.is_alive() and self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            self._thread.join(2)
        self._thread = None
        self._thread_id = None
