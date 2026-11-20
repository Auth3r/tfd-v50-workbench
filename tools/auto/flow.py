# -*- coding: utf-8 -*-
"""一条龙：等窗口 -> 标题 -> 跳动画 -> 选左角色 -> 长按跳过首任务 -> 确认 -> 观察。"""
import ctypes
import ctypes.wintypes as w
import os
import time

u = ctypes.windll.user32
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

OUT = r'C:\tfdwork\auto'
os.makedirs(OUT, exist_ok=True)


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
        score = wd * ht + (10 ** 7 if 'Descendant' in t else 0)
        if score > best_score:
            best_score = score
            best = (h, r)
    return best if best else (None, None)


VK = {'ENTER': 0x0D, 'ESC': 0x1B, 'SPACE': 0x20, 'O': 0x4F}


def focus(h):
    u.ShowWindow(h, 9)
    try:
        u.SetForegroundWindow(h)
    except Exception:
        pass
    u.BringWindowToTop(h)
    time.sleep(0.4)


def press(vk, hold=0.06):
    scan = u.MapVirtualKeyW(vk, 0)
    u.keybd_event(vk, scan, 0, 0)
    time.sleep(hold)
    u.keybd_event(vk, scan, 0x0002, 0)


def shot(name, rect):
    from PIL import ImageGrab
    img = ImageGrab.grab()
    c = img.crop((rect.l, rect.t, rect.r, rect.b))
    c.thumbnail((1100, 640))
    p = os.path.join(OUT, name)
    c.save(p, quality=82)
    print('SHOT', p, flush=True)


def brightness(rect):
    """粗判画面是否黑屏：取窗口中央区域算像素标准差。"""
    from PIL import ImageGrab, ImageStat
    img = ImageGrab.grab()
    c = img.crop((rect.l + (rect.r - rect.l) // 4, rect.t + (rect.b - rect.t) // 4,
                  rect.r - (rect.r - rect.l) // 4, rect.b - (rect.b - rect.t) // 4)).convert('L')
    c.thumbnail((160, 90))
    st = ImageStat.Stat(c)
    return st.stddev[0], st.mean[0]


def log(msg):
    print('[%s] %s' % (time.strftime('%H:%M:%S'), msg), flush=True)


h, r = find_game()
for _ in range(60):
    if h:
        break
    time.sleep(1)
    h, r = find_game()
if not h:
    log('NO GAME WINDOW')
    raise SystemExit(1)

log('window ok rect=%s' % ((r.l, r.t, r.r, r.b),))

# 黑屏门控：等画面真的有内容再开始按键（最多 70 秒）
for i in range(70):
    try:
        std, mean = brightness(r)
    except Exception:
        std, mean = 0, 0
    if std > 12:
        log('screen alive std=%.1f mean=%.1f after %ds' % (std, mean, i))
        break
    time.sleep(1)
else:
    log('SCREEN STILL BLACK after 70s, abort')
    shot('s_black.jpg', r)
    raise SystemExit(2)

shot('s0.jpg', r)
time.sleep(5)
shot('s0b.jpg', r)

focus(h)
press(VK['ENTER'])
log('ENTER')
time.sleep(10)
shot('s1.jpg', r)

for i in (2, 3, 4):
    focus(h)
    scan = u.MapVirtualKeyW(VK['ESC'], 0)
    u.keybd_event(VK['ESC'], scan, 0, 0)
    time.sleep(1.8)
    u.keybd_event(VK['ESC'], scan, 0x0002, 0)
    log('ESC hold #%d' % (i - 1))
    time.sleep(4)
    shot('s%d.jpg' % i, r)

focus(h)
x = int(r.l + (r.r - r.l) * 0.214)
y = int(r.t + (r.b - r.t) * 0.918)
u.SetCursorPos(x, y)
time.sleep(0.2)
u.mouse_event(0x0002, 0, 0, 0, 0)
time.sleep(0.08)
u.mouse_event(0x0004, 0, 0, 0, 0)
log('click char %d,%d' % (x, y))
time.sleep(4)
shot('s5.jpg', r)

focus(h)
x = int(r.l + (r.r - r.l) * 0.729)
y = int(r.t + (r.b - r.t) * 0.860)
u.SetCursorPos(x, y)
time.sleep(0.2)
u.mouse_event(0x0002, 0, 0, 0, 0)
time.sleep(2.0)
u.mouse_event(0x0004, 0, 0, 0, 0)
log('hold click skip-mission %d,%d' % (x, y))
time.sleep(5)
shot('s6.jpg', r)

focus(h)
press(VK['SPACE'])
log('SPACE confirm')
time.sleep(5)
shot('s7.jpg', r)

for i in range(1, 16):
    time.sleep(4)
    h2, r2 = find_game()
    if not h2:
        log('game window gone at loop %d' % i)
        break
    shot('loop%02d.jpg' % i, r2)
    log('loop %d' % i)

log('done')
