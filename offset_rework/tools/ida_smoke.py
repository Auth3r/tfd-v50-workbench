import json
import ida_auto
import ida_funcs
import ida_nalt
import idautils
import idc

ida_auto.auto_wait()
base = ida_nalt.get_imagebase()
n = 0
for ea in idautils.Functions():
    n += 1
print("smoke: functions=%d base=0x%x" % (n, base))
try:
    with open(r"E:\第二后裔\TFD发布端V50\TFD发布端V50\offset_rework\work\ida_smoke.json", "w", encoding="utf-8") as f:
        json.dump({"functions": n, "image_base": "0x%x" % base}, f)
except Exception as e:
    print("write failed: %s" % e)
idc.qexit(0)
