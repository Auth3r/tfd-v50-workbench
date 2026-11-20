# -*- coding: utf-8 -*-
"""点详情页第二条按钮"跳过第一个任务"：长按出确认弹窗 -> 空格 -> 连拍等世界。"""
import os
import sys
import time

import act
from PIL import ImageGrab

OUT = r'C:\tfdwork\auto'


def say(m):
    print('[%s] %s' % (time.strftime('%H:%M:%S'), m), flush=True)


def cap(name, r):
    im = ImageGrab.grab().crop((r.l, r.t, r.r, r.b))
    im.thumbnail((1100, 640))
    im.save(os.path.join(OUT, name), quality=82)
    say('shot ' + name)


h, r = act.find_game()
if not h:
    say('NO WINDOW')
    sys.exit(1)

img = ImageGrab.grab().crop((r.l, r.t, r.r, r.b)).convert('RGB')
W, H = img.size
px = img.load()
x0, x1 = int(W * 0.50), int(W * 0.95)
y0, y1 = int(H * 0.55), int(H * 0.95)

bands = []
cur = None
for y in range(y0, y1, 2):
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
    say('LESS THAN 2 BANDS')
    sys.exit(2)

b = bands[1]  # 第二条 = 跳过第一个任务
cy = (b[0] + b[1]) // 2
cx = int(sum(b[2]) / len(b[2]))
say('skip band y=%d..%d -> click %d,%d' % (b[0], b[1], r.l + cx, r.t + cy))

act.focus(h)
act.glide(r.l + cx, r.t + cy)
act.u.mouse_event(0x0002, 0, 0, 0, 0)
time.sleep(2.3)
act.u.mouse_event(0x0004, 0, 0, 0, 0)
time.sleep(1.5)
cap('s1.jpg', r)

act.focus(h)
act.press(act.VK['SPACE'])
say('SPACE')
time.sleep(2)
cap('s2.jpg', r)

for j in range(1, 8):
    time.sleep(5)
    h2, r2 = act.find_game()
    if not h2:
        say('窗口消失 %d' % j)
        break
    cap('y%d.jpg' % j, r2)
say('done')
