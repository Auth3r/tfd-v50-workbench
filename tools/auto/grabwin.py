# -*- coding: utf-8 -*-
"""激活游戏窗口并抓取窗口内某块区域（自动换算成绝对屏幕坐标）。"""
import ctypes
import ctypes.wintypes as w
import sys
import time

u = ctypes.windll.user32


class RECT(ctypes.Structure):
    _fields_ = [('l', ctypes.c_long), ('t', ctypes.c_long), ('r', ctypes.c_long), ('b', ctypes.c_long)]


def title(h):
    n = u.GetWindowTextLengthW(h)
    b = ctypes.create_unicode_buffer(n + 1)
    u.GetWindowTextW(h, b, n + 1)
    return b.value


def find_game():
    res = []
    cb = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)(lambda h, l: (res.append(h), True)[1])
    u.EnumWindows(cb, 0)
    for h in res:
        t = title(h)
        if u.IsWindowVisible(h) and ('Descendant' in t):
            r = RECT()
            u.GetWindowRect(h, ctypes.byref(r))
            if r.r - r.l > 300:
                return h, r
    return None, None


h, r = find_game()
if h is None:
    print('NO GAME')
    sys.exit(1)
u.ShowWindow(h, 9)
try:
    u.SetForegroundWindow(h)
except Exception:
    pass
u.BringWindowToTop(h)
time.sleep(0.8)

from PIL import ImageGrab

img = ImageGrab.grab()
out = sys.argv[1] if len(sys.argv) > 1 else r'C:\tfdwork\auto\win.jpg'
mode = sys.argv[2] if len(sys.argv) > 2 else 'full'
if mode == 'full':
    c = img.crop((r.l, r.t, r.r, r.b))
elif mode == 'bottom':
    c = img.crop((r.l + 300, r.b - 170, r.r - 300, r.b - 20)).resize((1400, 225))
elif mode == 'top':
    c = img.crop((r.l + 300, r.t + 20, r.r - 300, r.t + 170)).resize((1400, 225))
elif mode == 'center':
    cx, cy = (r.l + r.r) // 2, (r.t + r.b) // 2
    c = img.crop((cx - 600, cy - 300, cx + 600, cy + 300))
else:
    a, b2, cc, d = [int(x) for x in sys.argv[2:6]]
    c = img.crop((a, b2, cc, d))
c.thumbnail((1400, 800))
c.save(out, quality=85)
print('RECT', (r.l, r.t, r.r - r.l, r.b - r.t), '->', out, c.size)
