# -*- coding: utf-8 -*-
import ctypes, ctypes.wintypes as w
u = ctypes.windll.user32
res = []
EnumProc = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)(lambda h, l: (res.append(h), True)[1])
u.EnumWindows(EnumProc, 0)
class RECT(ctypes.Structure):
    _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long), ("r", ctypes.c_long), ("b", ctypes.c_long)]
rows = []
for h in res:
    n = u.GetWindowTextLengthW(h)
    if n == 0:
        continue
    buf = ctypes.create_unicode_buffer(n + 1)
    u.GetWindowTextW(h, buf, n + 1)
    t = buf.value
    if ('第一后裔' in t) or ('Descendant' in t) or ('M1-Win64' in t) or ('TFD' in t):
        r = RECT()
        u.GetWindowRect(h, ctypes.byref(r))
        rows.append((t, u.IsWindowVisible(h), u.IsIconic(h), r.l, r.t, r.r - r.l, r.b - r.t))
out = []
for r in rows:
    out.append("vis=%s min=%s rect=(%d,%d,%dx%d) title=%s" % (r[1], r[2], r[3], r[4], r[5], r[6], r[0]))
open(r"C:\tfdwork\wins.txt", "w", encoding="utf-8").write("\n".join(out) or "none")
print("\n".join(out) or "none")
