# -*- coding: utf-8 -*-
"""按时间轴抓游戏窗口：先把 The First Descendant 窗口提到前台，再 DXGI 抓全屏裁窗口区域"""
import ctypes, ctypes.wintypes as w, time, sys, os

u = ctypes.windll.user32
TITLE = "The First Descendant"


def find_hwnd():
    res = []
    EnumProc = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)(lambda h, l: (res.append(h), True)[1])
    u.EnumWindows(EnumProc, 0)
    for h in res:
        n = u.GetWindowTextLengthW(h)
        if n == 0:
            continue
        buf = ctypes.create_unicode_buffer(n + 1)
        u.GetWindowTextW(h, buf, n + 1)
        if buf.value.strip() == TITLE:
            return h
    return None


class RECT(ctypes.Structure):
    _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long), ("r", ctypes.c_long), ("b", ctypes.c_long)]


def rect_of(h):
    r = RECT()
    u.GetWindowRect(h, ctypes.byref(r))
    return r.l, r.t, r.r - r.l, r.b - r.t


def main():
    dur = int(sys.argv[1]) if len(sys.argv) > 1 else 90
    step = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    try:
        import dxcam
        from PIL import Image
    except Exception as e:
        print("import fail", e)
        return
    cam = dxcam.create(output_idx=0, output_color="BGRA")
    t0 = time.time()
    n = 0
    while time.time() - t0 < dur:
        h = find_hwnd()
        el = int(time.time() - t0)
        if h is None:
            print("t=%3ds  no window" % el, flush=True)
        else:
            l, t, w_, h_ = rect_of(h)
            u.ShowWindow(h, 9)  # SW_RESTORE
            u.SetForegroundWindow(h)
            time.sleep(0.5)
            frame = None
            for _ in range(6):
                frame = cam.grab()
                if frame is not None:
                    break
                time.sleep(0.2)
            if frame is None:
                print("t=%3ds  frame None rect=(%d,%d,%dx%d)" % (el, l, t, w_, h_), flush=True)
            else:
                img = Image.fromarray(frame[:, :, [2, 1, 0]].copy())
                crop = img.crop((l, t, l + w_, t + h_))
                crop.save(r"C:\tfdwork\dx_t_%02d.png" % n)
                px = crop.convert("L").point(lambda v: 255 if v > 18 else 0)
                nz = sum(px.getdata()) // 255
                print("t=%3ds  rect=(%d,%d,%dx%d) nonblack=%d/%d" % (el, l, t, w_, h_, nz, w_ * h_), flush=True)
                n += 1
        time.sleep(max(1, step - 0.5))
    print("done frames=%d" % n, flush=True)


main()
