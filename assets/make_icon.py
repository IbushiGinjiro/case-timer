"""アプリのアイコン（ドット絵）を作る。python assets/make_icon.py で case-timer.ico と確認用の png を出力する。

筐体（黄色・黒縁・角欠け）に START/STOP ボタンと液晶、右側にねじ。
16px と 32px はそれぞれ専用に描き、48px は 16px の3倍、256px は 32px の8倍に拡大する（ドットをぼかさない）。
"""
from pathlib import Path
from PIL import Image

C = {
    "K": "#1b1b1b", "Y": "#ffc21a", "H": "#ffe27a", "L": "#c98a00",
    "G": "#2bd14f", "g": "#8dff9f", "R": "#ff4141", "r": "#ff9c9c",
    "D": "#0f1a0f", "N": "#7dff6b", "S": "#bbbbbb", "s": "#777777",
}


def draw(n, rects):
    im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    px = im.load()
    for col, x0, y0, x1, y1 in rects:  # 両端を含む
        rgb = tuple(int(C[col][i:i + 2], 16) for i in (1, 3, 5)) + (255,) if col != "." else (0, 0, 0, 0)
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                px[x, y] = rgb
    return im


def case(x0, y0, x1, y1, w):
    """黒縁 w px・角を w px 欠いた筐体。内側に明るい縁（左上）と暗い縁（右下）。"""
    return [
        ("K", x0, y0, x1, y1),
        (".", x0, y0, x0 + w - 1, y0 + w - 1), (".", x1 - w + 1, y0, x1, y0 + w - 1),
        (".", x0, y1 - w + 1, x0 + w - 1, y1), (".", x1 - w + 1, y1 - w + 1, x1, y1),
        ("Y", x0 + w, y0 + w, x1 - w, y1 - w),
        ("H", x0 + w, y0 + w, x1 - w, y0 + w * 2 - 1), ("H", x0 + w, y0 + w, x0 + w * 2 - 1, y1 - w),
        ("L", x0 + w, y1 - w * 2 + 1, x1 - w, y1 - w), ("L", x1 - w * 2 + 1, y0 + w, x1 - w, y1 - w),
    ]


def icon16():
    return draw(16, case(0, 1, 12, 14, 1) + [
        ("K", 2, 3, 5, 7), ("G", 3, 4, 4, 6), ("g", 3, 4, 4, 4),
        ("K", 7, 3, 10, 7), ("R", 8, 4, 9, 6), ("r", 8, 4, 9, 4),
        ("K", 2, 9, 10, 12), ("D", 3, 10, 9, 11), ("N", 4, 10, 4, 11), ("N", 6, 10, 6, 11), ("N", 8, 10, 8, 11),
        ("s", 13, 6, 13, 8),
        ("K", 14, 4, 15, 10), ("S", 14, 5, 14, 9),
    ])


def icon32():
    return draw(32, case(0, 3, 25, 28, 2) + [
        ("K", 5, 7, 11, 15), ("G", 6, 8, 10, 14), ("g", 6, 8, 10, 9),
        ("K", 14, 7, 20, 15), ("R", 15, 8, 19, 14), ("r", 15, 8, 19, 9),
        ("K", 5, 18, 20, 24), ("D", 6, 19, 19, 23),
        ("N", 7, 20, 8, 22), ("N", 10, 20, 11, 22), ("N", 13, 20, 13, 20), ("N", 13, 22, 13, 22), ("N", 15, 20, 16, 22), ("N", 18, 20, 18, 22),
        ("K", 26, 12, 27, 18), ("s", 26, 13, 27, 17),
        ("K", 27, 8, 31, 22), ("S", 28, 9, 30, 21), ("s", 29, 9, 29, 21),
    ])


if __name__ == "__main__":
    here = Path(__file__).parent
    i16, i32 = icon16(), icon32()
    sizes = {16: i16, 32: i32, 48: i16.resize((48, 48), Image.NEAREST), 256: i32.resize((256, 256), Image.NEAREST)}
    sizes[256].save(here / "case-timer.ico", sizes=[(s, s) for s in sizes], append_images=[sizes[s] for s in (16, 32, 48)])
    sizes[256].save(here / "icon-256.png")
    # 確認用：16px と 32px を拡大して並べる
    prev = Image.new("RGBA", (16 * 12 + 32 * 6 + 30, 200), (255, 255, 255, 255))
    prev.alpha_composite(i16.resize((192, 192), Image.NEAREST), (4, 4))
    prev.alpha_composite(i32.resize((192, 192), Image.NEAREST), (220, 4))
    prev.save(here / "icon-preview.png")
    print("ok")
