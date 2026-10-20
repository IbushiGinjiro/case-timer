"""記録の修正行・追加行の時刻／時間の入力欄（電卓式・範囲選択・全角が入らない等）を自動操作で確認する。

使い方は analysis_screens.py と同じ。結果は標準出力に「操作 → 表示・枠の中身・カーソル位置」で出る。
"""
import ctypes, os, sys, threading, time
ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))
os.environ["CASE_TIMER_DATA_DIR"] = sys.argv[1]
OUT = sys.argv[2]
from app import main as m
from PIL import ImageGrab
m.App.MAIN_TITLE, m.App.ANALYSIS_TITLE = "ct-e2e-main", "ct-e2e-analysis"
u = ctypes.windll.user32
app = m.App()
def shot(name):
    # 他のウィンドウが重なっていても、このウィンドウの中身だけを撮る（PrintWindow + PW_RENDERFULLCONTENT）
    from PIL import Image
    g = ctypes.windll.gdi32
    hwnd = u.FindWindowW(None, app.ANALYSIS_TITLE); r = m.RECT(); u.GetWindowRect(hwnd, ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    hdc = u.GetWindowDC(hwnd); mdc = g.CreateCompatibleDC(hdc); bmp = g.CreateCompatibleBitmap(hdc, w, h); g.SelectObject(mdc, bmp)
    u.PrintWindow(hwnd, mdc, 2)
    class BIH(ctypes.Structure):
        _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32), ("biHeight", ctypes.c_int32), ("biPlanes", ctypes.c_uint16), ("biBitCount", ctypes.c_uint16),
                    ("biCompression", ctypes.c_uint32), ("biSizeImage", ctypes.c_uint32), ("a", ctypes.c_int32), ("b", ctypes.c_int32), ("c", ctypes.c_uint32), ("d", ctypes.c_uint32)]
    bi = BIH(); bi.biSize = ctypes.sizeof(BIH); bi.biWidth = w; bi.biHeight = -h; bi.biPlanes = 1; bi.biBitCount = 32
    buf = ctypes.create_string_buffer(w * h * 4)
    g.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0)
    Image.frombuffer("RGB", (w, h), buf, "raw", "BGRX", 0, 1).save(os.path.join(OUT, name + ".png"))
    g.DeleteObject(bmp); g.DeleteDC(mdc); u.ReleaseDC(hwnd, hdc)
js = lambda c: app.analysis.evaluate_js(c)
KEY = "window.key=(el,k)=>el.dispatchEvent(new KeyboardEvent('keydown',{key:k,bubbles:true,cancelable:true}));1"
def drive():
    try:
        time.sleep(4); app.open_analysis(); time.sleep(5)
        u.ShowWindow(u.FindWindowW(None, app.MAIN_TITLE), 6)
        js("window.__errs=[];window.addEventListener('error',e=>__errs.push(e.message));Element.prototype.setPointerCapture=function(){};window.pe=(el,t,x,y)=>el.dispatchEvent(new PointerEvent(t,{bubbles:true,clientX:x,clientY:y,pointerId:1,button:0}));window.drag=(el,dx,dy,n=10)=>{const r=el.getBoundingClientRect();const x=r.left+r.width/2,y=r.top+r.height/2;pe(el,'pointerdown',x,y);for(let i=1;i<=n;i++)pe(el,'pointermove',x+dx*i/n,y+dy*i/n);pe(el,'pointerup',x+dx,y+dy);};1"); js(KEY)
        js("document.querySelectorAll('#tabLever .labels span')[2].click()"); time.sleep(1)
        st = lambda el: js(f"[{el}.value,{el}.dataset.slots,{el}.selectionStart].join(' ')")
        # 修正：開始 10:01 の時を Backspace で消す → 分は残る
        js("document.querySelector('.slide[data-i=\"1\"]').dispatchEvent(new MouseEvent('dblclick',{bubbles:true}))"); time.sleep(0.5)
        print("init", st("fS"), js("fCalc.textContent"))
        js("fS.focus();['Delete'].forEach(k=>key(fS,k));fS.setSelectionRange(0,5);key(fS,'Delete');['1','2','0','1'].forEach(k=>key(fS,k))"); print("set 12:01", st("fS"))
        js("fS.setSelectionRange(3,4);key(fS,'2')"); print("select min tens + 2 -> 12:21", st("fS"))
        js("fS.setSelectionRange(0,5);key(fS,'Delete');['1','2','0','1'].forEach(k=>key(fS,k));fS.setSelectionRange(4,5);key(fS,'2')"); print("select min ones + 2 -> 12:02", st("fS"))
        js("fS.setSelectionRange(0,2);key(fS,'0');key(fS,'9')"); print("select hours + 0 9 -> 09:02", st("fS"))
        js("fS.setSelectionRange(0,5);['1','2','3','0'].forEach(k=>key(fS,k))"); print("select all + 1230", st("fS"))
        js("fS.focus();fS.setSelectionRange(3,5);key(fS,'Backspace')"); print("select minutes + BS (10:01)", st("fS"))
        js("fS.setSelectionRange(0,2);key(fS,'0');key(fS,'9')"); print("select hours + 0 9", st("fS"))
        js("fS.setSelectionRange(0,5);key(fS,'1')"); print("select all + 1", st("fS"))
        js("fS.setSelectionRange(0,5);key(fS,'Delete')"); print("select all + Delete", st("fS"))
        js("fS.setSelectionRange(0,0);['１','３','あ','Process'].forEach(k=>key(fS,k))"); print("zenkaku keys ignored", st("fS"))
        js("['1','3'].forEach(k=>key(fS,k))"); print("13", st("fS"))
        print("editable?", js("fS.isContentEditable"), js("fS.tagName"))
        js("key(fS,'Home');key(fS,'ArrowRight');key(fS,'ArrowRight');fS.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight',shiftKey:true,bubbles:true,cancelable:true}))"); print("arrows+shift", st("fS"), js("fS.selectionEnd"))
        js("fS.setSelectionRange(3,3);key(fS,'3');key(fS,'0')"); print("minutes 30", st("fS"), js("fCalc.textContent"))
        js("['a','A','-',' '].forEach(k=>key(fS,k))"); print("letters ignored", st("fS"), js("fS.type"))
        js("fS.setSelectionRange(0,5);key(fS,'Delete');['0','8','4','5'].forEach(k=>key(fS,k))"); print("0845", st("fS"), js("fCalc.textContent"))
        shot("h_password_field")
        js("key(fE,'Escape')"); js("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))"); time.sleep(0.5)
        # 追加：-:-- に分だけ 3 0 → 保存で 0:30
        js("drag(document.querySelector('.slide[data-i=\"2\"]'),0,40)"); time.sleep(0.5)
        print("new init", st("fDur"))
        js("fDur.setSelectionRange(2,2);key(fDur,'3');key(fDur,'0')"); print("minutes only", st("fDur"))
        js("key(fDur,'Enter')"); time.sleep(1.5)
        print("saved", js("[...document.querySelectorAll('#recs .slide.notime')].map(r=>r.textContent.replace(/\s+/g,' ')).join('|')"))
        # 追加：1 3 0 で 1:30（時のあと「:」を越えて分へ）
        js("drag(document.querySelector('.slide[data-i=\"2\"]'),0,40)"); time.sleep(0.5)
        js("['1','3','0'].forEach(k=>key(fDur,k))"); print("130", st("fDur"))
        js("fDur.setSelectionRange(1,1);key(fDur,'Backspace')"); print("dur bs hour", st("fDur"))
        js("key(fDur,'2')"); print("dur type 2", st("fDur"))
        js("key(fDur,'9')"); print("dur type 9 ignored", st("fDur"))
        js("key(fDur,'Escape')")
        print("errors", js("JSON.stringify(__errs)"))
    except Exception:
        import traceback; traceback.print_exc()
    finally:
        app.analysis.destroy(); app.main.destroy()
threading.Thread(target=drive, daemon=True).start()
app.run()
