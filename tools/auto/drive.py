# -*- coding: utf-8 -*-
"""TFD 自动化驱动：找窗口 / 截图 / 发键鼠。

用法：
  python drive.py win                  # 列出候选窗口
  python drive.py shot out.jpg         # 截图（M1 优先，否则启动器）
  python drive.py focus                # 激活窗口
  python drive.py key O 1              # 发送按键（支持 O/SPACE/ENTER/ESC/F1..）
  python drive.py click 640 400        # 绝对屏幕坐标左键
  python drive.py macro enter 90       # 进主城连打：先 O，再空格/回车轮询
"""
import ctypes
import ctypes.wintypes as w
import os
import sys
import time

u = ctypes.windll.user32
OUT = r'C:\tfdwork\auto'
os.makedirs(OUT, exist_ok=True)


class RECT(ctypes.Structure):
    _fields_ = [('l', ctypes.c_long), ('t', ctypes.c_long), ('r', ctypes.c_long), ('b', ctypes.c_long)]


def title(h):
    n = u.GetWindowTextLengthW(h)
    buf = ctypes.create_unicode_buffer(n + 1)
    u.GetWindowTextW(h, buf, n + 1)
    return buf.value


def windows():
    res = []
    cb = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)(lambda h, l: (res.append(h), True)[1])
    u.EnumWindows(cb, 0)
    out = []
    for h in res:
        t = title(h)
        if not t or not u.IsWindowVisible(h):
            continue
        r = RECT()
        u.GetWindowRect(h, ctypes.byref(r))
        wd, ht = r.r - r.l, r.b - r.t
        if wd < 200 or ht < 120:
            continue
        out.append((h, t, (r.l, r.t, r.r, r.b)))
    return out


def pick():
    ws = windows()
    for h, t, r in ws:
        if 'Descendant' in t or t.startswith('M1'):
            return h, t, r
    for h, t, r in ws:
        if 'TFD' in t or '启动器' in t or 'Launcher' in t:
            return h, t, r
    return None


def focus(h):
    u.ShowWindow(h, 9)
    try:
        u.SetForegroundWindow(h)
    except Exception:
        pass
    time.sleep(0.2)
    return u.GetForegroundWindow() == h


VK = {
    'O': 0x4F, 'SPACE': 0x20, 'ENTER': 0x0D, 'ESC': 0x1B, 'TAB': 0x09,
    'F1': 0x70, 'F2': 0x71, 'W': 0x57, 'A': 0x41, 'S': 0x53, 'D': 0x44,
    'M': 0x4D, 'UP': 0x26, 'DOWN': 0x28, 'LEFT': 0x25, 'RIGHT': 0x27,
}


def key(vk, hold=0.05):
    scan = u.MapVirtualKeyW(vk, 0)
    u.keybd_event(vk, scan, 0, 0)
    time.sleep(hold)
    u.keybd_event(vk, scan, 0x0002, 0)
    time.sleep(0.05)


def click(x, y):
    u.SetCursorPos(int(x), int(y))
    time.sleep(0.15)
    u.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.05)
    u.mouse_event(0x0004, 0, 0, 0, 0)


def shot(path, region=None):
    try:
        import dxcam
        cam = dxcam.create(output_color='RGB')
        if region is None:
            img = cam.grab()
        else:
            img = cam.grab(region=region)
        del cam
    except Exception:
        from PIL import ImageGrab
        img = ImageGrab.grab(bbox=region)
    if img is None:
        return False
    from PIL import Image
    im = Image.fromarray(img) if not hasattr(img, 'save') else img
    im = im.convert('RGB')
    im.thumbnail((1280, 720))
    p = path if os.path.isabs(path) else os.path.join(OUT, path)
    im.save(p, quality=80)
    print('SHOT', p, im.size)
    return True


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'win'
    h = pick()
    if cmd == 'win':
        for hh, t, r in windows():
            print('hwnd=%s rect=%s title=%r' % (hh, r, t))
        return
    if h is None:
        print('NO WINDOW')
        return
    hid, ht, rect = h
    print('TARGET hwnd=%s rect=%s title=%r' % (hid, rect, ht))
    if cmd == 'shot':
        name = sys.argv[2] if len(sys.argv) > 2 else 'shot.jpg'
        shot(name, region=rect)
        return
    if cmd == 'focus':
        print('focused', focus(hid))
        return
    if cmd == 'key':
        k = sys.argv[2].upper() if len(sys.argv) > 2 else 'O'
        n = int(sys.argv[3]) if len(sys.argv) > 3 else 1
        focus(hid)
        for _ in range(n):
            key(VK[k])
            time.sleep(0.4)
        print('KEY', k, n)
        return
    if cmd == 'click':
        x, y = int(sys.argv[2]), int(sys.argv[3])
        focus(hid)
        click(x, y)
        print('CLICK', x, y)
        return
    if cmd == 'macro':
        dur = int(sys.argv[3]) if len(sys.argv) > 3 else 90
        focus(hid)
        t0 = time.time()
        key(VK['O'], 0.25)
        print('macro O sent')
        idx = 0
        next_shot = t0 + 2
        while time.time() - t0 < dur:
            now = time.time()
            if now >= next_shot:
                idx += 1
                shot(os.path.join(OUT, 'f%02d.jpg' % idx), region=rect)
                next_shot += 2.0
                if idx % 2 == 1:
                    key(VK['SPACE'])
                else:
                    key(VK['ENTER'])
                print('frame %d sent %s' % (idx, 'SPACE' if idx % 2 == 1 else 'ENTER'))
            time.sleep(0.25)
        print('macro done frames=%d' % idx)
        return
    print('unknown cmd')


if __name__ == '__main__':
    main()
