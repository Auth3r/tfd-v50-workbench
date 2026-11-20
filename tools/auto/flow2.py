# -*- coding: utf-8 -*-
"""一键走完 标题->过场->选人->跳过首任务->确认，全程带截图。"""
import os
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
    say('shot %s' % name)


def clickn(r, nx, ny):
    x = int(r.l + (r.r - r.l) * nx)
    y = int(r.t + (r.b - r.t) * ny)
    act.glide(x, y)
    act.u.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.08)
    act.u.mouse_event(0x0004, 0, 0, 0, 0)
    say('click %d,%d' % (x, y))


def holdclickn(r, nx, ny, sec=2.5):
    x = int(r.l + (r.r - r.l) * nx)
    y = int(r.t + (r.b - r.t) * ny)
    act.glide(x, y)
    act.u.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(sec)
    act.u.mouse_event(0x0004, 0, 0, 0, 0)
    say('holdclick %d,%d %.1fs' % (x, y, sec))


h, r = act.find_game()
for _ in range(80):
    if h:
        break
    time.sleep(1)
    h, r = act.find_game()
if not h:
    say('NO GAME')
    raise SystemExit(1)
say('window %s' % ((r.l, r.t, r.r - r.l, r.b - r.t),))

act.focus(h)
clickn(r, 0.5, 0.55)      # 先点一下激活窗口
time.sleep(2)
act.focus(h)
act.press(act.VK['ENTER'])
say('ENTER')
time.sleep(8)
cap('p1.jpg', r)

for i in range(1, 4):
    act.focus(h)
    scan = act.u.MapVirtualKeyW(act.VK['ESC'], 0)
    act.u.keybd_event(act.VK['ESC'], scan, 0, 0)
    time.sleep(2.2)
    act.u.keybd_event(act.VK['ESC'], scan, 0x0002, 0)
    say('ESC hold %d' % i)
    time.sleep(4)
    cap('p%d.jpg' % (i + 1), r)

act.focus(h)
clickn(r, 0.214, 0.875)   # 维艾莎
time.sleep(4)
cap('p5.jpg', r)

holdclickn(r, 0.729, 0.838, 2.6)   # 跳过第一个任务
time.sleep(3.5)
cap('p6.jpg', r)

act.focus(h)
act.press(act.VK['SPACE'])
say('SPACE confirm')
time.sleep(3)
cap('p7.jpg', r)

for i in range(1, 13):
    time.sleep(4)
    h2, r2 = act.find_game()
    if not h2:
        say('game gone at loop %d' % i)
        break
    cap('q%02d.jpg' % i, r2)
say('done')
