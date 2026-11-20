# -*- coding: utf-8 -*-
"""自动化主循环：起栈 -> 读 native_account_loaded 判定这局是否会黑 ->
黑就立刻杀掉重开 -> 正常则走 UI（回车/跳过过场/选维艾莎/开始第一个任务）-> 连拍。"""
import json
import os
import subprocess
import sys
import time

import act
from PIL import ImageGrab, ImageStat

ROOT = r'E:\第二后裔\TFD发布端V50\TFD发布端V50'
ACC = '04f2858b03d3e1f379515d84ba575f03'
RUNS = os.path.join(ROOT, 'data', 'launcher', 'runs', ACC)
LOG = os.path.join(ROOT, 'patch_v50.log')
PY = sys.executable
OUT = r'C:\tfdwork\auto'
MAX_TRY = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 4


def say(m):
    print('[%s] %s' % (time.strftime('%H:%M:%S'), m), flush=True)


def run_dirs():
    try:
        return {d for d in os.listdir(RUNS) if os.path.isdir(os.path.join(RUNS, d))}
    except Exception:
        return set()


def kill_all():
    subprocess.run(['taskkill', '/F', '/IM', 'M1-Win64-Shipping.exe'], capture_output=True)
    subprocess.run(['taskkill', '/F', '/IM', 'TFDLauncher.exe'], capture_output=True)


def procs_left():
    out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq M1-Win64-Shipping.exe'],
                         capture_output=True, text=True)
    a = 'M1-Win64' in (out.stdout or '')
    out2 = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq TFDLauncher.exe'],
                          capture_output=True, text=True)
    return a or ('TFDLauncher' in (out2.stdout or ''))


def kill_helpers():
    """残留的 inject/patch/prio python 会占住启动器的实例锁，必须一起清掉。"""
    subprocess.run(['powershell', '-NoProfile', '-Command',
                    "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
                    "Where-Object { $_.CommandLine -match 'inject_v50|patch_v50|prio_watch' } | "
                    "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"],
                   capture_output=True)


def hard_kill():
    for _ in range(4):
        kill_helpers()
        kill_all()
        time.sleep(3)
        if not procs_left():
            return True
    return False


def clear_locks():
    p = os.path.join(ROOT, 'data', 'launcher', 'launcher.lock')
    try:
        os.remove(p)
    except Exception:
        pass
    saves = os.path.join(ROOT, 'data', 'launcher', 'saves')
    for d, _, fs in os.walk(saves):
        if 'launcher.lock' in fs:
            try:
                os.remove(os.path.join(d, 'launcher.lock'))
            except Exception:
                pass


def lp_alive():
    out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq TFDLauncher.exe'], capture_output=True, text=True)
    return 'TFDLauncher' in (out.stdout or '')


def start_stack():
    before = run_dirs()
    env = os.environ.copy()
    env['TFD_PY'] = PY                       # 关键：cmd 里 find_python 会挑到豆包沙箱那个坏 ctypes
    env['PATH'] = PY + os.pathsep + env.get('PATH', '')
    subprocess.run(['cmd', '/c', '启动V50（免授权）.cmd'], cwd=ROOT, env=env, capture_output=True)
    time.sleep(25)
    say('launcher alive=%s' % lp_alive())
    subprocess.Popen([PY, '-B', r'C:\tfdwork\prio_watch.py'],
                     stdout=open(r'C:\tfdwork\prioV.txt', 'a'), stderr=subprocess.STDOUT,
                     creationflags=0x08000000)
    subprocess.Popen([PY, '-B', os.path.join(ROOT, 'inject_v50.py')], cwd=ROOT,
                     creationflags=0x08000000)
    # run 目录要等客户端被拉起来才建，轮询最多 60s
    t0 = time.time()
    while time.time() - t0 < 60:
        new = [d for d in run_dirs() - before if d != 'latest']
        if new:
            return os.path.join(RUNS, new[0])
        time.sleep(2)
    return None


def account_loaded(run_dir, timeout=90):
    """返回 (elapsed, character_count)；超时返回 (None, None)。"""
    f = os.path.join(run_dir, 'events.jsonl')
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with open(f, 'r', encoding='utf-8', errors='ignore') as fh:
                for line in fh:
                    if 'native_account_loaded' in line:
                        ev = json.loads(line)
                        return float(ev.get('elapsed', 0)), int(ev.get('character_count', -1))
        except Exception:
            pass
        time.sleep(1)
    return None, None


def bright(r):
    img = ImageGrab.grab()
    c = img.crop((r.l + (r.r - r.l) // 5, r.t + (r.b - r.t) // 5,
                  r.r - (r.r - r.l) // 5, r.b - (r.b - r.t) // 5)).convert('L')
    c.thumbnail((200, 110))
    return ImageStat.Stat(c).stddev[0]


def cap(name, r):
    img = ImageGrab.grab()
    c = img.crop((r.l, r.t, r.r, r.b))
    c.thumbnail((1100, 640))
    c.save(os.path.join(OUT, name), quality=82)
    say('shot ' + name)


def clickn(r, nx, ny):
    x = int(r.l + (r.r - r.l) * nx)
    y = int(r.t + (r.b - r.t) * ny)
    act.glide(x, y)
    act.u.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.08)
    act.u.mouse_event(0x0004, 0, 0, 0, 0)
    say('click %d,%d' % (x, y))


def esc_hold(h, sec=2.2):
    act.focus(h)
    scan = act.u.MapVirtualKeyW(act.VK['ESC'], 0)
    act.u.keybd_event(act.VK['ESC'], scan, 0, 0)
    time.sleep(sec)
    act.u.keybd_event(act.VK['ESC'], scan, 0x0002, 0)


os.makedirs(OUT, exist_ok=True)
log_f = open(r'C:\tfdwork\auto_run.log', 'a', encoding='utf-8')
_orig = sys.stdout


class Tee:
    def write(self, s):
        _orig.write(s)
        log_f.write(s)
        log_f.flush()

    def flush(self):
        _orig.flush()
        log_f.flush()


sys.stdout = Tee()

run_dir = None
for attempt in range(1, MAX_TRY + 1):
    say('== 第 %d 轮 ==' % attempt)
    if not hard_kill():
        say('杀不干净，再等一次')
        time.sleep(6)
    clear_locks()
    run_dir = start_stack()
    if not run_dir:
        say('没拿到新 run 目录，重来')
        continue
    say('run=%s' % os.path.basename(run_dir))
    el, cc = account_loaded(run_dir, timeout=100)
    if el is None:
        say('等不到 native_account_loaded，重来')
        continue
    say('native_account_loaded elapsed=%.2fs chars=%d' % (el, cc))
    if el > 30.0:
        say('=> 这局必黑（加载慢），自动重开')
        continue
    break
else:
    say('轮次用完，全部是慢加载黑屏局')
    sys.exit(3)

# --- 正常局，走 UI ---
h, r = None, None
deadline = time.time() + 30
while time.time() < deadline:
    h, r = act.find_game()
    if h:
        break
    time.sleep(1)
if not h:
    say('NO WINDOW')
    sys.exit(1)

say('窗口已就绪，等画面')
deadline = time.time() + 40
while time.time() < deadline:
    if bright(r) > 12:
        break
    time.sleep(1)
cap('k0.jpg', r)

act.focus(h)
clickn(r, 0.5, 0.55)
time.sleep(2)
act.focus(h)
act.press(act.VK['ENTER'])
say('ENTER')
time.sleep(16)
cap('k1.jpg', r)

for i in range(1, 5):
    esc_hold(h)
    say('esc %d' % i)
    time.sleep(3.5)
    cap('k%d.jpg' % (i + 1), r)

time.sleep(2)
act.focus(h)
clickn(r, 0.214, 0.875)   # 维艾莎（左）
time.sleep(3)
cap('m1.jpg', r)

# 详情页：点第二条按钮 = 跳过第一个任务，长按 2.3s 出确认弹窗，再空格
img = ImageGrab.grab().crop((r.l, r.t, r.r, r.b)).convert('RGB')
W, H = img.size
px = img.load()
x0, x1 = int(W * 0.50), int(W * 0.95)
bands = []
cur = None
for y in range(int(H * 0.55), int(H * 0.95), 2):
    hit = 0
    xs = []
    for x in range(x0, x1, 4):
        p = px[x, y]
        if p[2] > 90 and p[2] - p[0] > 30 and p[2] - p[1] > 8:
            hit += 1
            xs.append(x)
    if hit > 25:
        if cur is None:
            cur = [y, y, xs]
        else:
            cur[1] = y
            cur[2].extend(xs)
    else:
        if cur and cur[1] - cur[0] > 8:
            bands.append(cur)
        cur = None
if cur and cur[1] - cur[0] > 8:
    bands.append(cur)
say('bands=%d' % len(bands))
if len(bands) < 2:
    say('详情页没找到两条按钮，停')
    sys.exit(4)

b = bands[1]
cy = (b[0] + b[1]) // 2
cx = int(sum(b[2]) / len(b[2]))
say('跳过按钮 -> %d,%d' % (r.l + cx, r.t + cy))
act.glide(r.l + cx, r.t + cy)
act.u.mouse_event(0x0002, 0, 0, 0, 0)
time.sleep(2.3)
act.u.mouse_event(0x0004, 0, 0, 0, 0)
time.sleep(1.5)
cap('m2.jpg', r)
act.focus(h)
act.press(act.VK['SPACE'])
say('SPACE 确认跳过')
time.sleep(2)
cap('m3.jpg', r)

for j in range(1, 7):
    time.sleep(5)
    h2, r2 = act.find_game()
    if not h2:
        say('窗口消失 %d' % j)
        break
    cap('w%d.jpg' % j, r2)

say('UI 走完，收集事件')
try:
    with open(os.path.join(run_dir, 'events.jsonl'), 'r', encoding='utf-8', errors='ignore') as fh:
        for line in fh:
            if any(k in line for k in ('private_world', 'client_exit', 'connection_rejected',
                                       'client_session_detached', 'client_exit_observed')):
                say(line.strip()[:300])
except Exception as e:
    say('读事件失败 %s' % e)
say('done')
