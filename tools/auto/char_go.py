# -*- coding: utf-8 -*-
"""在创角页选维艾莎 -> 详情页点开始第一个任务 -> 连拍等世界。"""
import os
import sys
import time

import act
from PIL import ImageGrab

OUT = r'C:\tfdwork\auto'


def say(m):
    print('[%s] %s' % (time.strftime('%H:%M:%S'), m), flush=True)


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


h, r = act.find_game()
if not h:
    say('NO WINDOW')
    sys.exit(1)

act.focus(h)
clickn(r, 0.214, 0.875)
time.sleep(3)
cap('n1.jpg', r)
clickn(r, 0.729, 0.750)
time.sleep(3)
cap('n2.jpg', r)

for j in range(1, 7):
    time.sleep(5)
    h2, r2 = act.find_game()
    if not h2:
        say('窗口消失 %d' % j)
        break
    cap('x%d.jpg' % j, r2)
say('done')
