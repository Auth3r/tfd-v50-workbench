"""禁用「同步更新版本 / 加群」弹窗；若已弹出，则点它的「我已知晓」按钮（不关窗口）。"""
import ctypes
import sys
import threading
import time
import traceback
from ctypes import wintypes

LOG = r'C:\Users\0\licagent\kill_notice_run.log'


def w(msg):
    try:
        with open(LOG, 'a', encoding='utf-8') as fh:
            fh.write('%s %s\n' % (time.strftime('%H:%M:%S'), msg))
    except Exception:
        pass


try:
    try:
        import launcher_branding as LB
        LB.show_release_notice = lambda *a, **k: None
        for name in ('DEFAULT_GROUP', 'GROUP_WATERMARK', 'RELEASE_STATEMENT'):
            if hasattr(LB, name):
                setattr(LB, name, '')
        w('launcher_branding 已清理（弹窗+常量）')
    except Exception as e:
        w('禁用失败: %r' % (e,))
    try:
        import launcher as L
        if getattr(L, 'show_release_notice', None) is not None:
            L.show_release_notice = lambda *a, **k: None
        for name in ('DEFAULT_GROUP', 'GROUP_WATERMARK'):
            if hasattr(L, name):
                setattr(L, name, '')
        w('launcher 常量已清空')
    except Exception:
        pass

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    pid_me = kernel32.GetCurrentProcessId()

    INPUT_MOUSE = 0
    LEFTDOWN = 0x0002
    LEFTUP = 0x0004

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [('dx', wintypes.LONG), ('dy', wintypes.LONG),
                    ('mouseData', wintypes.DWORD), ('dwFlags', wintypes.DWORD),
                    ('time', wintypes.DWORD), ('dwExtraInfo', ctypes.POINTER(wintypes.ULONG))]

    class INPUT(ctypes.Structure):
        _fields_ = [('type', wintypes.DWORD), ('mi', MOUSEINPUT)]

    def click(hwnd, cw, ch):
        pt = wintypes.POINT(int(cw * 0.5), int(ch * 0.82))
        user32.ClientToScreen(hwnd, ctypes.byref(pt))
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.15)
        user32.SetCursorPos(pt.x, pt.y)
        time.sleep(0.1)

        def send(flags):
            inp = INPUT()
            inp.type = INPUT_MOUSE
            inp.mi = MOUSEINPUT(0, 0, 0, flags, 0, None)
            user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

        send(LEFTDOWN)
        time.sleep(0.06)
        send(LEFTUP)
        w('已点击「我已知晓」@%d,%d' % (pt.x, pt.y))

    def worker():
        end = time.time() + 120
        clicked = 0
        while time.time() < end:
            hits = []

            @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            def cb(hwnd, lp):
                p = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
                if p.value == pid_me and user32.IsWindowVisible(hwnd):
                    t = ctypes.create_unicode_buffer(256)
                    user32.GetWindowTextW(hwnd, t, 256)
                    if '更新' in t.value or '加群' in t.value:
                        rc = wintypes.RECT()
                        user32.GetClientRect(hwnd, ctypes.byref(rc))
                        hits.append((hwnd, rc.right, rc.bottom, t.value))
                return True

            try:
                user32.EnumWindows(cb, 0)
            except Exception:
                pass
            for hwnd, cw, ch, title in hits:
                if clicked < 5:
                    w('发现弹窗 %r %dx%d' % (title, cw, ch))
                    try:
                        click(hwnd, cw, ch)
                        clicked += 1
                    except Exception as e:
                        w('点击失败 %r' % (e,))
            time.sleep(1.0)

    threading.Thread(target=worker, daemon=True).start()
    w('处理线程已启动 (pid=%s)' % pid_me)
except Exception:
    w('FATAL: ' + traceback.format_exc()[-600:])
