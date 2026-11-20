# -*- coding: utf-8 -*-
"""在已存活会话上长按 ESC 若干次，逐次截图，找出创角页。"""
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
    say('shot %s' % name)


h, r = act.find_game()
if not h:
    say('NO WINDOW')
    sys.exit(1)

n = int(sys.argv[1]) if len(sys.argv) > 1 else 4
for i in range(n):
    act.focus(h)
    scan = act.u.MapVirtualKeyW(act.VK['ESC'], 0)
    act.u.keybd_event(act.VK['ESC'], scan, 0, 0)
    time.sleep(2.2)
    act.u.keybd_event(act.VK['ESC'], scan, 0x0002, 0)
    say('esc %d' % (i + 1))
    time.sleep(3.0)
    cap('e%d.jpg' % (i + 1), r)
say('done')
