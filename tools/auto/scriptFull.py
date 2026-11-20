# -*- coding: utf-8 -*-
"""全流程一键：黑屏则快速失败(exit 2)；正常则 标题->跳过过场->选人->开始第一个任务->等世界。"""
import os
import sys
import time

import act
from PIL import ImageGrab, ImageStat

OUT = r'C:\tfdwork\auto'


def say(m):
    print('[%s] %s' % (time.strftime('%H:%M:%S'), m), flush=True)


def cap(name, r):
    img = ImageGrab.grab()
    c = img.crop((r.l, r.t, r.r, r.b))
    c.thumbnail((1100, 640))
    c.save(os.path.join(OUT, name), quality=82)
    say('shot %s' % name)


def bright(r):
    img = ImageGrab.grab()
    c = img.crop((r.l + (r.r - r.l) // 5, r.t + (r.b - r.t) // 5,
                  r.r - (r.r - r.l) // 5, r.b - (r.b - r.t) // 5)).convert('L')
    c.thumbnail((160, 90))
    return ImageStat.Stat(c).stddev[0]


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
    say('esc hold')


h, r = act.find_game()
deadline = time.time() + 90
while time.time() < deadline:
    h, r = act.find_game()
    if h:
        break
    time.sleep(1)
if not h:
    say('NO WINDOW')
    sys.exit(1)

# 黑屏门控
deadline = time.time() + 40
while time.time() < deadline:
    try:
        s = bright(r)
    except Exception:
        s = 0
    if s > 12:
        say('screen alive std=%.1f' % s)
        break
    time.sleep(1)
else:
    cap('black.jpg', r)
    say('BLACK BOOT')
    sys.exit(2)

act.focus(h)
clickn(r, 0.5, 0.55)
time.sleep(2)
act.focus(h)
act.press(act.VK['ENTER'])
say('ENTER')
time.sleep(14)
cap('b1.jpg', r)

for i in range(4):
    try:
        s = bright(r)
    except Exception:
        s = 0
    if s > 10:
        esc_hold(h)
        time.sleep(3.5)
        cap('b%d.jpg' % (i + 2), r)
    else:
        time.sleep(2)

time.sleep(3)
cap('b6.jpg', r)

clickn(r, 0.214, 0.875)
time.sleep(3)
cap('b7.jpg', r)

clickn(r, 0.729, 0.750)
time.sleep(3)
cap('b8.jpg', r)

for i in range(1, 7):
    time.sleep(5)
    h2, r2 = act.find_game()
    if not h2:
        say('window gone %d' % i)
        break
    cap('c%02d.jpg' % i, r2)
say('done')
