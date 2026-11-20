# -*- coding: utf-8 -*-
"""在窗口画面里找蓝色按钮条（自下而上），点最上面那条的中心。用于详情页"开始第一个任务"。"""
import os
import sys
import time

import act
from PIL import ImageGrab

OUT = r'C:\tfdwork\auto'


def say(m):
    print('[%s] %s' % (time.strftime('%H:%M:%S'), m), flush=True)


h, r = act.find_game()
if not h:
    say('NO WINDOW')
    sys.exit(1)

img = ImageGrab.grab().crop((r.l, r.t, r.r, r.b)).convert('RGB')
W, H = img.size
px = img.load()
x0, x1 = int(W * 0.50), int(W * 0.95)
y0, y1 = int(H * 0.55), int(H * 0.95)
step = 2

bands = []
cur = None
for y in range(y0, y1, step):
    hit = 0
    xs = []
    for x in range(x0, x1, 4):
        p = px[x, y]
        if p[2] > 90 and p[2] - p[0] > 30 and p[2] - p[1] > 8:
            hit += 1
            xs.append(x)
    if hit > 25 and (x1 - x0) // 4 * 0.25 < hit:
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
if not bands:
    say('NO BAND')
    sys.exit(2)

b = bands[0]
cy = (b[0] + b[1]) // 2
cx = int(sum(b[2]) / len(b[2]))
say('band y=%d..%d -> click %d,%d (norm %.3f,%.3f)' % (b[0], b[1], r.l + cx, r.t + cy,
                                                       cx / W, cy / H))
act.focus(h)
act.glide(r.l + cx, r.t + cy)
act.u.mouse_event(0x0002, 0, 0, 0, 0)
time.sleep(0.12)
act.u.mouse_event(0x0004, 0, 0, 0, 0)
time.sleep(2)

img = ImageGrab.grab().crop((r.l, r.t, r.r, r.b))
img.thumbnail((1100, 640))
img.save(os.path.join(OUT, 'p1.jpg'), quality=82)
say('shot p1.jpg')
for j in range(1, 7):
    time.sleep(5)
    h2, r2 = act.find_game()
    if not h2:
        say('窗口消失 %d' % j)
        break
    im = ImageGrab.grab().crop((r2.l, r2.t, r2.r, r2.b))
    im.thumbnail((1100, 640))
    im.save(os.path.join(OUT, 'z%d.jpg' % j), quality=82)
    say('shot z%d.jpg' % j)
say('done')
