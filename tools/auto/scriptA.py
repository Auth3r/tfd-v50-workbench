# -*- coding: utf-8 -*-
"""标题 -> 等 logo 播完 -> 两次长按 ESC -> 截图停在选人页。"""
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


h, r = act.find_game()
for _ in range(90):
    if h:
        break
    time.sleep(1)
    h, r = act.find_game()
if not h:
    say('NO GAME')
    raise SystemExit(1)

act.focus(h)
act.glide(int(r.l + (r.r - r.l) * 0.5), int(r.t + (r.b - r.t) * 0.55))
act.u.mouse_event(0x0002, 0, 0, 0, 0)
time.sleep(0.08)
act.u.mouse_event(0x0004, 0, 0, 0, 0)
time.sleep(2)
act.focus(h)
act.press(act.VK['ENTER'])
say('ENTER')
time.sleep(16)
cap('a1.jpg', r)

for i in (1, 2):
    act.focus(h)
    scan = act.u.MapVirtualKeyW(act.VK['ESC'], 0)
    act.u.keybd_event(act.VK['ESC'], scan, 0, 0)
    time.sleep(2.2)
    act.u.keybd_event(act.VK['ESC'], scan, 0x0002, 0)
    say('ESC hold %d' % i)
    time.sleep(4)
    cap('a%d.jpg' % (i + 1), r)

time.sleep(4)
cap('a4.jpg', r)
say('done')
