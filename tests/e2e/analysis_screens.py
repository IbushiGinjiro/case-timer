"""実アプリで分析画面を開き、3画面・追加・削除・修正・ダイヤルを自動操作して確認する。

使い方：python tests/e2e/analysis_screens.py <seed_dummy.pyで作ったデータフォルダ> <スクリーンショットの出力先>
ウィンドウのタイトルを別名にするので、インストール版が起動していても干渉しない（ショートカットが重なる確認ダイアログは出る）。
撮影は PrintWindow で分析画面だけを撮る（画面の見たままを撮ると、前にある別の作業画面が写るため）。
"""
import ctypes, os, sys, threading, time, json
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
def js(code):
    return app.analysis.evaluate_js(code)
def drive():
    try:
        time.sleep(4)
        app.open_analysis(); time.sleep(5)
        u.ShowWindow(u.FindWindowW(None, app.MAIN_TITLE), 6)
        u.SetForegroundWindow(u.FindWindowW(None, app.ANALYSIS_TITLE)); time.sleep(1)
        js("window.__errs=[];window.addEventListener('error',e=>__errs.push(e.message));Element.prototype.setPointerCapture=function(){};"
           "window.pe=(el,t,x,y)=>el.dispatchEvent(new PointerEvent(t,{bubbles:true,clientX:x,clientY:y,pointerId:1,button:0}));"
           "window.drag=(el,dx,dy,n=10)=>{const r=el.getBoundingClientRect();const x=r.left+r.width/2,y=r.top+r.height/2;pe(el,'pointerdown',x,y);for(let i=1;i<=n;i++)pe(el,'pointermove',x+dx*i/n,y+dy*i/n);pe(el,'pointerup',x+dx,y+dy);};1")
        print("period(graph)", js("document.getElementById('period').textContent"))
        shot("a_graph")
        js("document.querySelectorAll('#tabLever .labels span')[1].click()"); time.sleep(1)
        print("result head", js("document.getElementById('resHead').textContent"), "| total row", js("document.querySelector('#resBody tr.total').textContent"))
        shot("b_result")
        js("document.querySelectorAll('#resLever .labels span')[3].click()"); time.sleep(0.5)
        print("result ALL head", js("document.getElementById('resHead').textContent"))
        js("document.querySelectorAll('#tabLever .labels span')[2].click()"); time.sleep(1)
        print("rec rows", js("document.querySelectorAll('#recs .slide').length"), js("document.getElementById('recNote').textContent"))
        print("notime row", js("[...document.querySelectorAll('#recs .slide.notime')].map(r=>r.textContent.replace(/\s+/g,' ')).join('|')"))
        # 追加：2行目を引き下げ → 1行の入力行 → 1 3 0 Enter
        js("drag(document.querySelector('.slide[data-i=\"2\"]'),0,40)"); time.sleep(0.5)
        print("form", js("document.querySelectorAll('.newbox .row').length"), js("[...document.querySelectorAll('#fD option')].map(o=>o.value).join(',')||document.getElementById('fD').dataset.v"))
        shot("c_record_form")
        js("const d=document.getElementById('fDur');['1','3','0','Enter'].forEach(k=>d.dispatchEvent(new KeyboardEvent('keydown',{key:k,bubbles:true,cancelable:true})))"); time.sleep(1.5)
        print("after save notime", js("[...document.querySelectorAll('#recs .slide.notime')].map(r=>r.textContent.replace(/\s+/g,' ')).join('|')"))
        # 削除：右へ引いて帯を押す
        n0 = js("document.querySelectorAll('#recs .slide').length")
        js("drag(document.querySelector('.slide[data-i=\"0\"]'),90,0)"); time.sleep(0.8)
        js("document.querySelector('.delband').click()"); time.sleep(1.5)
        print("delete", n0, "->", js("document.querySelectorAll('#recs .slide').length"))
        # ダブルクリックで修正 → Esc
        js("document.querySelector('.slide[data-i=\"0\"]').dispatchEvent(new MouseEvent('dblclick',{bubbles:true}))"); time.sleep(0.5)
        print("edit form", js("!!document.getElementById('fS')"), js("document.getElementById('fS')?.value"))
        shot("d_record_edit")
        js("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))"); time.sleep(0.5)
        # ダイヤル：目盛りクリックで WK
        js("document.querySelectorAll('#tabLever .labels span')[0].click()"); time.sleep(0.8)
        js("document.querySelectorAll('#dial .mark:not(.dot)')[0].click()"); time.sleep(0.8)
        print("dial WK", js("document.getElementById('period').textContent"))
        print("errors", js("JSON.stringify(window.__errs)"))
        shot("e_graph_week")
    except Exception as e:
        import traceback; traceback.print_exc()
    finally:
        app.analysis.destroy(); app.main.destroy()
threading.Thread(target=drive, daemon=True).start()
app.run()
