"""第一后裔 V50 独立启动器（GUI）

- GUI 用系统 Python 3.12（带 tkinter）
- 注入用 patch 运行库 Python（带 frida），以子进程方式调用
"""
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path

HERE = Path(r'E:\The First Descendant\TFD发布端V50')
CORE_EXE = HERE / 'TFDLauncher.exe'
INJECTOR = HERE / 'inject_v50.py'
ACCOUNT_TXT = HERE / 'account.txt'
PATCH_LOG = HERE / 'patch_v50.log'

PATCH_PY = Path(r'E:\The First Descendant\The First Descendant\TFD-Offline\.tfd-patch'
                r'\releases\1.0.7-c2cafd1f3ee39906\runtime\python.exe')

GAME_NAME = 'M1-Win64-Shipping.exe'
CORE_NAME = 'TFDLauncher.exe'
NO_WINDOW = 0x08000000
SW_HIDE = 0


def hide_core_window(duration=30):
    """把核心启动器的窗口藏起来，只保留本启动器界面。"""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    hidden = set()
    found = []
    WM = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(hwnd, lp):
        try:
            if not user32.IsWindowVisible(hwnd):
                return True
            t = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, t, 256)
            if t.value and ('后裔' in t.value or 'TFD' in t.value.upper()):
                found.append(hwnd)
        except Exception:
            pass
        return True

    _CB = WM(cb)          # 保持引用，避免被回收
    end = time.time() + duration
    while time.time() < end:
        found.clear()
        try:
            user32.EnumWindows(_CB, 0)
            for h in list(found):
                if h not in hidden:
                    user32.ShowWindow(h, SW_HIDE)
                    hidden.add(h)
        except Exception:
            pass
        time.sleep(0.6)


def proc_running(name):
    try:
        out = subprocess.check_output(['tasklist', '/FI', 'IMAGENAME eq %s' % name],
                                      creationflags=NO_WINDOW, stderr=subprocess.DEVNULL)
        return name.lower().encode() in out.lower()
    except Exception:
        return False


class App:
    def __init__(self, root):
        self.root = root
        root.title('第一后裔 V50 启动器')
        root.geometry('760x560')
        root.minsize(680, 500)
        self.busy = False

        frm = ttk.Frame(root, padding=14)
        frm.pack(fill='both', expand=True)
        frm.columnconfigure(1, weight=1)

        ttk.Label(frm, text='账号').grid(row=0, column=0, sticky='w')
        self.account = tk.StringVar(value=self._read_account())
        ttk.Entry(frm, textvariable=self.account, width=26).grid(
            row=0, column=1, sticky='w', padx=8, pady=4)
        ttk.Label(frm, text='（可换号：改这里后点保存，重启生效）',
                  foreground='#888').grid(row=0, column=2, sticky='w')

        ttk.Label(frm, text='游戏路径').grid(row=1, column=0, sticky='w')
        self.exe = tk.StringVar(value=self._read_exe())
        ttk.Entry(frm, textvariable=self.exe, width=60).grid(
            row=1, column=1, sticky='we', padx=8, pady=4)
        ttk.Button(frm, text='浏览', command=self.browse, width=8).grid(row=1, column=2, sticky='w')

        btns = ttk.Frame(frm)
        btns.grid(row=2, column=0, columnspan=3, sticky='we', pady=(12, 8))
        self.btn_start = ttk.Button(btns, text='  启动游戏  ', command=self.start)
        self.btn_start.pack(side='left')
        self.btn_stop = ttk.Button(btns, text='  停止  ', command=self.stop)
        self.btn_stop.pack(side='left', padx=10)
        ttk.Button(btns, text='保存账号', command=self.save).pack(side='left')
        ttk.Button(btns, text='打开数据目录', command=self.opendata).pack(side='left', padx=10)

        self.status = tk.StringVar(value='就绪')
        ttk.Label(frm, textvariable=self.status, foreground='#0a5').grid(
            row=3, column=0, columnspan=3, sticky='w', pady=(2, 8))

        ttk.Label(frm, text='运行日志').grid(row=4, column=0, sticky='w')
        self.log = tk.Text(frm, height=18, wrap='none', font=('Consolas', 9))
        sb = ttk.Scrollbar(frm, command=self.log.yview)
        self.log.configure(yscrollcommand=sb.set)
        self.log.grid(row=5, column=0, columnspan=2, sticky='nsew')
        sb.grid(row=5, column=2, sticky='ns')
        frm.rowconfigure(5, weight=1)

        self._say('启动器就绪')
        self._say('点击「启动游戏」：自动注入补丁 → 起服务 → 拉起客户端')
        self._tail()

    def _read_account(self):
        try:
            if ACCOUNT_TXT.exists():
                parts = ACCOUNT_TXT.read_text(encoding='utf-8').strip().split()
                if parts and parts[0].lower() != 'manual':
                    return parts[0]
        except Exception:
            pass
        return 'demo'

    def _read_exe(self):
        return (r'E:\The First Descendant\The First Descendant\客户端'
                r'\The First Descendant.part01\The First Descendant'
                r'\M1\Binaries\Win64\M1-Win64-Shipping.exe')

    def _say(self, msg):
        self.log.insert('end', '[%s] %s\n' % (time.strftime('%H:%M:%S'), msg))
        self.log.see('end')

    def browse(self):
        p = filedialog.askopenfilename(title='选择游戏主程序',
                                       filetypes=[('exe', '*.exe')])
        if p:
            self.exe.set(p)

    def save(self):
        try:
            ACCOUNT_TXT.write_text('%s 12345678\n' % (self.account.get().strip() or 'demo'),
                                   encoding='utf-8')
            self._say('已保存账号：%s' % self.account.get().strip())
        except Exception as e:
            messagebox.showerror('保存失败', str(e))

    def opendata(self):
        try:
            os.startfile(str(HERE / 'data'))
        except Exception as e:
            messagebox.showerror('打开失败', str(e))

    def _tail(self):
        def run():
            seen = 0
            while True:
                try:
                    if PATCH_LOG.exists():
                        size = PATCH_LOG.stat().st_size
                        if size != seen:
                            lines = PATCH_LOG.read_text(encoding='utf-8', errors='replace').splitlines()
                            for ln in (lines if seen == 0 else lines[-5:]):
                                self._say('  ' + ln)
                            seen = size
                except Exception:
                    pass
                time.sleep(1.2)
        threading.Thread(target=run, daemon=True).start()

    def start(self):
        if self.busy:
            return
        self.busy = True
        self.btn_start.config(state='disabled')
        self.status.set('启动中…')
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        try:
            user = self.account.get().strip() or 'demo'
            ACCOUNT_TXT.write_text('%s 12345678\n' % user, encoding='utf-8')
            self._say('账号：%s' % user)

            if not proc_running(CORE_NAME):
                self._say('启动核心进程（窗口会被隐藏）…')
                subprocess.Popen([str(CORE_EXE)], cwd=str(HERE), creationflags=NO_WINDOW)
                threading.Thread(target=hide_core_window, kwargs={'duration': 45},
                                 daemon=True).start()
                time.sleep(9)
            else:
                self._say('核心进程已在运行')
                threading.Thread(target=hide_core_window, kwargs={'duration': 20},
                                 daemon=True).start()

            if not PATCH_PY.exists():
                self._say('找不到注入运行库：%s' % PATCH_PY)
                self.status.set('启动失败')
                return

            self._say('注入补丁…')
            p = subprocess.run([str(PATCH_PY), '-B', str(INJECTOR)],
                               cwd=str(HERE), creationflags=NO_WINDOW,
                               capture_output=True, timeout=180)
            out = (p.stdout or b'').decode('utf-8', 'replace').strip()
            if out:
                for ln in out.splitlines()[:8]:
                    self._say('  注入: ' + ln)

            self.status.set('等待客户端启动…')
            for _ in range(60):
                if proc_running(GAME_NAME):
                    self._say('客户端已启动')
                    self.status.set('游戏运行中')
                    return
                time.sleep(2)
            self.status.set('等待超时，请查看日志')
        except Exception as e:
            self._say('异常：%r' % (e,))
            self.status.set('启动失败')
        finally:
            self.busy = False
            self.btn_start.config(state='normal')

    def stop(self):
        try:
            os.system('taskkill /IM %s /F >nul 2>&1' % GAME_NAME)
            time.sleep(1)
            os.system('taskkill /IM %s /F >nul 2>&1' % CORE_NAME)
            self._say('已停止客户端与核心进程')
            self.status.set('已停止')
        except Exception as e:
            self._say('停止失败：%r' % (e,))


def main():
    root = tk.Tk()
    try:
        root.iconbitmap(default='')
    except Exception:
        pass
    App(root)
    root.mainloop()


if __name__ == '__main__':
    main()
