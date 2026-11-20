# -*- coding: utf-8 -*-
"""对游戏窗口执行键鼠动作（自动置前台），并可顺手截图。

  python act.py key ENTER
  python act.py hold ESC 1.6
  python act.py clickn 0.22 0.55      # 窗口内归一化坐标点击
  python act.py shot out.jpg [full|bottom|top|center]
"""
import ctypes
import ctypes.wintypes as w
import sys
import time

u = ctypes.windll.user32
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        u.SetProcessDPIAware()
    except Exception:
        pass


class RECT(ctypes.Structure):
    _fields_ = [('l', ctypes.c_long), ('t', ctypes.c_long), ('r', ctypes.c_long), ('b', ctypes.c_long)]


def title(h):
    n = u.GetWindowTextLengthW(h)
    b = ctypes.create_unicode_buffer(n + 1)
    u.GetWindowTextW(h, b, n + 1)
    return b.value


def m1_pids():
    TH32CS_SNAPPROCESS = 0x00000002
    k = ctypes.windll.kernel32

    class PE32(ctypes.Structure):
        _fields_ = [('dwSize', ctypes.c_ulong), ('cntUsage', ctypes.c_ulong), ('th32ProcessID', ctypes.c_ulong),
                    ('th32DefaultHeapID', ctypes.c_void_p), ('th32ModuleID', ctypes.c_ulong),
                    ('cntThreads', ctypes.c_ulong), ('th32ParentProcessID', ctypes.c_ulong),
                    ('pcPriClassBase', ctypes.c_long), ('dwFlags', ctypes.c_ulong),
                    ('szExeFile', ctypes.c_char * 260)]

    snap = k.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    pe = PE32()
    pe.dwSize = ctypes.sizeof(PE32)
    pids = set()
    if k.Process32First(snap, ctypes.byref(pe)):
        while True:
            name = pe.szExeFile.decode('mbcs', 'ignore').lower()
            if 'm1-win64-shipping.exe' in name:
                pids.add(int(pe.th32ProcessID))
            if not k.Process32Next(snap, ctypes.byref(pe)):
                break
    k.CloseHandle(snap)
    return pids


def find_game():
    pids = m1_pids()
    res = []
    cb = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)(lambda h, l: (res.append(h), True)[1])
    u.EnumWindows(cb, 0)
    best = None
    best_score = -1
    for h in res:
        r = RECT()
        u.GetWindowRect(h, ctypes.byref(r))
        wd, ht = r.r - r.l, r.b - r.t
        if wd < 300 or ht < 200:
            continue
        pid = w.DWORD()
        u.GetWindowThreadProcessId(h, ctypes.byref(pid))
        t = title(h)
        if not (pid.value in pids or 'Descendant' in t):
            continue
        # 控制台窗口标题是 exe 路径，真正的游戏窗口标题含 Descendant 且更大
        score = wd * ht + (10 ** 7 if 'Descendant' in t else 0)
        if score > best_score:
            best_score = score
            best = (h, r)
    return best if best else (None, None)


VK = {
    'O': 0x4F, 'SPACE': 0x20, 'ENTER': 0x0D, 'ESC': 0x1B, 'TAB': 0x09, 'F': 0x46,
    'W': 0x57, 'A': 0x41, 'S': 0x53, 'D': 0x44, 'M': 0x4D,
    'UP': 0x26, 'DOWN': 0x28, 'LEFT': 0x25, 'RIGHT': 0x27, 'ESC2': 0x1B,
}


def topmost(h):
    """置顶，防止聊天窗口把游戏盖住（否则截图全抓到别的窗口、按键也打错对象）。"""
    HWND_TOPMOST = -1
    SWP_NOMOVE = 0x0002
    SWP_NOSIZE = 0x0001
    u.SetWindowPos(h, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | 0x0040)


def focus(h):
    topmost(h)
    u.ShowWindow(h, 9)
    try:
        fg = u.GetForegroundWindow()
        if fg and fg != h:
            k = ctypes.windll.kernel32
            fg_tid = u.GetWindowThreadProcessId(fg, None)
            my_tid = k.GetCurrentThreadId()
            k.AttachThreadInput(my_tid, fg_tid, True)
            u.SetForegroundWindow(h)
            u.BringWindowToTop(h)
            u.SetFocus(h)
            k.AttachThreadInput(my_tid, fg_tid, False)
        else:
            u.SetForegroundWindow(h)
    except Exception:
        pass
    time.sleep(0.5)
    print('FG=%r target=%r' % (title(u.GetForegroundWindow()), title(h)))


def press(vk, hold=0.06):
    scan = u.MapVirtualKeyW(vk, 0)
    u.keybd_event(vk, scan, 0, 0)
    time.sleep(hold)
    u.keybd_event(vk, scan, 0x0002, 0)
    time.sleep(0.08)


def shot(path, rect, mode='full'):
    from PIL import ImageGrab
    img = ImageGrab.grab()
    if mode == 'full':
        c = img.crop((rect.l, rect.t, rect.r, rect.b))
    elif mode == 'bottom':
        c = img.crop((rect.l + 200, rect.b - 160, rect.r - 200, rect.b - 10)).resize((1400, 216))
    elif mode == 'top':
        c = img.crop((rect.l + 200, rect.t + 10, rect.r - 200, rect.t + 160)).resize((1400, 216))
    elif mode == 'center':
        cx, cy = (rect.l + rect.r) // 2, (rect.t + rect.b) // 2
        c = img.crop((cx - 700, cy - 380, cx + 700, cy + 380))
    else:
        c = img.crop((rect.l, rect.t, rect.r, rect.b))
    c.thumbnail((1400, 800))
    c.save(path, quality=85)
    print('SHOT', path, c.size)


def glide(x, y, steps=10):
    """相对移动靠近目标，让游戏收到真实的 mousemove（瞬移不会触发悬停）。"""
    u.SetCursorPos(max(0, x - steps), max(0, y - steps))
    time.sleep(0.05)
    for _ in range(steps):
        u.mouse_event(0x0001, 1, 1, 0, 0)
        time.sleep(0.02)
    time.sleep(0.1)


def main():
    cmd = sys.argv[1]
    h, r = find_game()
    if h is None:
        print('NO GAME')
        return
    if cmd == 'shot':
        path = sys.argv[2]
        mode = sys.argv[3] if len(sys.argv) > 3 else 'full'
        shot(path, r, mode)
        return
    if cmd == 'info':
        print('rect', r.l, r.t, r.r - r.l, r.b - r.t)
        cr = RECT()
        u.GetClientRect(h, ctypes.byref(cr))
        print('client', cr.r - cr.l, cr.b - cr.t)
        pt = w.POINT()
        u.ClientToScreen(h, ctypes.byref(pt))
        print('client_origin', pt.x, pt.y)
        try:
            print('dpi', u.GetDpiForWindow(h))
        except Exception:
            print('dpi ?')
        print('screen', u.GetSystemMetrics(0), u.GetSystemMetrics(1))
        from PIL import ImageGrab
        g = ImageGrab.grab()
        print('grab', g.size)
        return
    focus(h)
    if cmd == 'key':
        k = sys.argv[2].upper()
        press(VK[k])
        print('KEY', k)
    elif cmd == 'hold':
        k = sys.argv[2].upper()
        sec = float(sys.argv[3]) if len(sys.argv) > 3 else 1.5
        scan = u.MapVirtualKeyW(VK[k], 0)
        u.keybd_event(VK[k], scan, 0, 0)
        time.sleep(sec)
        u.keybd_event(VK[k], scan, 0x0002, 0)
        print('HOLD', k, sec)
    elif cmd == 'clickn':
        nx, ny = float(sys.argv[2]), float(sys.argv[3])
        x = int(r.l + (r.r - r.l) * nx)
        y = int(r.t + (r.b - r.t) * ny)
        u.SetCursorPos(x, y)
        time.sleep(0.2)
        u.mouse_event(0x0002, 0, 0, 0, 0)
        time.sleep(0.08)
        u.mouse_event(0x0004, 0, 0, 0, 0)
        print('CLICK', x, y)
    elif cmd == 'hover':
        nx, ny = float(sys.argv[2]), float(sys.argv[3])
        x = int(r.l + (r.r - r.l) * nx)
        y = int(r.t + (r.b - r.t) * ny)
        glide(x, y)
        print('HOVER', x, y)
    elif cmd == 'holdclickn':
        nx, ny = float(sys.argv[2]), float(sys.argv[3])
        sec = float(sys.argv[4]) if len(sys.argv) > 4 else 1.8
        x = int(r.l + (r.r - r.l) * nx)
        y = int(r.t + (r.b - r.t) * ny)
        glide(x, y)
        u.mouse_event(0x0002, 0, 0, 0, 0)
        time.sleep(sec)
        u.mouse_event(0x0004, 0, 0, 0, 0)
        print('HOLDCLICK', x, y, sec)


if __name__ == '__main__':
    main()
