# -*- coding: utf-8 -*-
"""放大截取游戏窗口内的归一化区域：python zoom.py 0.38 0.78 0.62 0.85 out.png [scale]"""
import sys
import time

import act
from PIL import ImageGrab

h, r = act.find_game()
if h is None:
    print('NO GAME')
    raise SystemExit(1)
x0, y0, x1, y1 = [float(v) for v in sys.argv[1:5]]
out = sys.argv[5]
scale = int(sys.argv[6]) if len(sys.argv) > 6 else 4
act.focus(h)
time.sleep(0.3)
img = ImageGrab.grab()
box = (int(r.l + (r.r - r.l) * x0), int(r.t + (r.b - r.t) * y0),
       int(r.l + (r.r - r.l) * x1), int(r.t + (r.b - r.t) * y1))
c = img.crop(box)
c = c.resize((c.width * scale, c.height * scale))
c.save(out, quality=90)
print('zoom', box, c.size)
